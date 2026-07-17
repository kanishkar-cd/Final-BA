from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.agents.epic_agent_2 import EpicGenerationAgent
from app.agents.requirement_analysis_agent import RequirementAnalysisAgent
from app.agents.story_validation_agent import StoryValidationAgent
from app.agents.user_story_agent import UserStoryGenerationAgent
from app.chunking.chunk_service import ChunkService
from app.labeling.context_labeler import ContextLabeler
from app.orchestrator.langgraph_adapters import (
    DeferredRequirementAnalyzer,
    EpicFeatureAdapter,
    EpicOneLineStoryAdapter,
    WorkflowStateAdapter,
)
from app.orchestrator.langgraph_state import WorkflowState
from app.schemas import Chunk
from app.schemas.user_story import OneLineStoryInput, PlanningArtifact
from app.services.import_service import DocumentImportService
from app.services.preprocessing_pipeline_service import DocumentPreprocessingPipelineService

# Monkeypatch RequirementAnalysisAgent to support BaseAgent execute contract
RequirementAnalysisAgent.execute = RequirementAnalysisAgent.run
RequirementAnalysisAgent.__abstractmethods__ = frozenset()


class DocumentImporter(Protocol):
    async def import_document(self, file_path: str | Path) -> str:
        """Return parsed document text."""


class Chunker(Protocol):
    def chunk_text(
        self,
        text: str,
        *,
        document_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
        source: str | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Return semantic chunks."""


class ContextLabelerProtocol(Protocol):
    async def label_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """Return context-labeled chunks."""


class PreprocessingService(Protocol):
    async def run(
        self,
        file_path: str | Path,
        *,
        document_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
    ) -> Any:
        """Run document preprocessing and return a preprocessing response."""


class FeatureGenerator(Protocol):
    async def execute(self, state: WorkflowState) -> list[PlanningArtifact]:
        """Return generated feature artifacts."""


class OneLineStoryGenerator(Protocol):
    async def execute(self, state: WorkflowState) -> list[OneLineStoryInput]:
        """Return generated one-line story artifacts."""


@dataclass(slots=True)
class WorkflowNodes:
    """LangGraph node wrappers for backend services and agents."""

    importer: DocumentImporter | None = None
    chunker: Chunker | None = None
    context_labeler: ContextLabelerProtocol | None = None
    preprocessing_service: PreprocessingService | None = None
    requirement_agent: RequirementAnalysisAgent | None = None
    epic_agent: EpicGenerationAgent | None = None
    feature_generator: FeatureGenerator | None = None
    one_line_story_generator: OneLineStoryGenerator | None = None
    user_story_agent: UserStoryGenerationAgent | None = None
    validation_agent: StoryValidationAgent | None = None
    state_adapter: WorkflowStateAdapter | None = None

    _preprocessing_service: PreprocessingService = field(init=False, repr=False)
    _requirement_agent: RequirementAnalysisAgent = field(init=False, repr=False)
    _epic_agent: EpicGenerationAgent = field(init=False, repr=False)
    _feature_generator: FeatureGenerator = field(init=False, repr=False)
    _one_line_story_generator: OneLineStoryGenerator = field(init=False, repr=False)
    _user_story_agent: UserStoryGenerationAgent = field(init=False, repr=False)
    _validation_agent: StoryValidationAgent = field(init=False, repr=False)
    _state_adapter: WorkflowStateAdapter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._preprocessing_service = (
            self.preprocessing_service or self._create_preprocessing_service()
        )
        self._requirement_agent = self.requirement_agent or RequirementAnalysisAgent()
        self._epic_agent = self.epic_agent or EpicGenerationAgent()
        self._feature_generator = self.feature_generator or EpicFeatureAdapter()
        self._one_line_story_generator = (
            self.one_line_story_generator or EpicOneLineStoryAdapter()
        )
        self._user_story_agent = self.user_story_agent or UserStoryGenerationAgent()
        self._validation_agent = self.validation_agent or StoryValidationAgent()
        self._state_adapter = self.state_adapter or WorkflowStateAdapter()

    async def preprocessing(self, state: WorkflowState) -> WorkflowState:
        file_path = state.get("file_path")
        if file_path is None:
            if state.get("retrieved_chunks") or state.get("epics") or state.get("agent1_output"):
                return {}
            raise ValueError("WorkflowState.file_path is required for preprocessing.")

        response = await self._preprocessing_service.run(
            file_path,
            document_id=state.get("document_id"),
            project_id=state.get("project_id"),
        )
        return self._state_adapter.preprocessing_response_to_state(
            response,
            document_id=state.get("document_id"),
            project_id=state.get("project_id"),
        )

    async def requirement_analysis(self, state: WorkflowState) -> WorkflowState:
        if state.get("requirement_analysis") or state.get("agent1_output"):
            return {}
        output = await self._requirement_agent.run(state.get("requirement_chunks", []))
        return self._state_adapter.requirement_analysis_to_state(
            output,
            retrieved_chunks=state.get("retrieved_chunks", []),
        )

    async def epic_generation(self, state: WorkflowState) -> WorkflowState:
        if state.get("epics") or state.get("agent2_output"):
            return {}
        output = await self._epic_agent.execute(state.get("requirement_analysis", {}))
        return self._state_adapter.epic_generation_to_state(output)

    async def feature_generation(self, state: WorkflowState) -> WorkflowState:
        if state.get("features"):
            return {}
        return {"features": await self._feature_generator.execute(state)}

    async def one_line_story_generation(self, state: WorkflowState) -> WorkflowState:
        if state.get("one_line_stories"):
            return {}
        one_line_stories = await self._one_line_story_generator.execute(state)
        return self._state_adapter.one_line_stories_to_state(
            one_line_stories,
            epics=state.get("epics", []),
            features=state.get("features", []),
            retrieved_chunks=state.get("retrieved_chunks", []),
            agent1_output=state.get("agent1_output"),
            traceability=state.get("traceability", {}),
        )

    async def user_story_generation(self, state: WorkflowState) -> WorkflowState:
        existing_stories = state.get("user_stories") or []
        has_generation_failures = any(
            getattr(story, "metadata", {}).get("generation_status") == "FAILED"
            for story in existing_stories
        )
        if existing_stories and not has_generation_failures:
            return {}
        request = self._state_adapter.generation_request_from_state(state)
        user_stories = await self._user_story_agent.execute(request)
        return {
            "generation_request": request,
            "user_stories": user_stories,
        }

    async def validation(self, state: WorkflowState) -> WorkflowState:
        validation_request = self._state_adapter.validation_request_from_state(state)
        validation_result = await self._validation_agent.execute(validation_request)

        retry_count = int(state.get("retry_count", 0))
        max_retry_attempts = int(state.get("max_retry_attempts", 3))

        from app.regeneration.retry_service import RetryService
        retry_service = RetryService()
        if retry_service.should_retry(validation_result, retry_count, max_retry_attempts):
            retry_count += 1

        # Update state's user_stories list with calculated confidence scores
        user_stories = list(state.get("user_stories", []))
        if user_stories and validation_result.story_results:
            story_scores = {res.story_id: res.confidence_score for res in validation_result.story_results}
            for i, story in enumerate(user_stories):
                story_id = story.get("id") if isinstance(story, dict) else getattr(story, "id", None)
                if story_id in story_scores:
                    if isinstance(story, dict):
                        story["confidence_score"] = story_scores[story_id]
                    else:
                        story.confidence_score = story_scores[story_id]

        return {
            "validation_result": validation_result,
            "retry_count": retry_count,
            "user_stories": user_stories,
        }

    async def guardrails_hook(self, state: WorkflowState) -> WorkflowState:
        return {"guardrails": {**state.get("guardrails", {}), "status": "not_configured"}}

    async def nlp_rag_hook(self, state: WorkflowState) -> WorkflowState:
        traceability = state.get("traceability") or {}
        if not isinstance(traceability, dict):
            traceability = {}
        else:
            traceability = dict(traceability)

        rag_context = traceability.get("rag_context")
        if not isinstance(rag_context, dict):
            rag_context = {}
            traceability["rag_context"] = rag_context
        else:
            rag_context = dict(rag_context)

        project_id = state.get("project_id")
        document_id = state.get("document_id")
        epics = state.get("epics") or []
        features = state.get("features") or []
        one_line_stories = state.get("one_line_stories") or []

        try:
            import time
            from app.rag.bm25_service import BM25Service
            from app.rag.vector_store_service import VectorStoreService
            from app.rag.embedding_service import EmbeddingService
            from app.rag.dense_retrieval_service import DenseRetrievalService
            from app.rag.hybrid_retrieval_service import HybridRetrievalService
            from app.rag.rrf_service import RRFService
            from app.rag.reranker_service import RerankerService
            from app.rag.context_builder import ContextBuilder
            from app.utils.logger import get_logger

            logger = get_logger("orchestrator.nlp_rag_hook")
            logger.info("Initializing RAG services for nlp_rag_hook...")

            bm25 = BM25Service()
            vs = VectorStoreService()
            emb = EmbeddingService()
            dense = DenseRetrievalService(emb, vs)
            hybrid = HybridRetrievalService(bm25, dense)
            rrf = RRFService()
            reranker = RerankerService()
            cb = ContextBuilder()
        except Exception as exc:
            import logging
            logger = logging.getLogger("orchestrator.nlp_rag_hook")
            logger.warning("RAG services could not be initialized inside orchestrator: %s. Continuing pipeline without RAG context.", exc)
            return {"traceability": traceability, "rag_context": rag_context}

        epic_lookup = {
            (getattr(epic, "id", None) or epic.get("id")): epic
            for epic in epics
            if (getattr(epic, "id", None) or epic.get("id")) is not None
        }
        feature_lookup = {
            (getattr(feature, "id", None) or feature.get("id")): feature
            for feature in features
            if (getattr(feature, "id", None) or feature.get("id")) is not None
        }

        all_chunks = []
        all_business_rules = []
        all_dependencies = []
        all_requirements = []

        for story in one_line_stories:
            story_id = (
                story.get("id")
                if hasattr(story, "get")
                else getattr(story, "id", None)
            )
            story_feature_id = (
                story.get("feature_id")
                if hasattr(story, "get")
                else getattr(story, "feature_id", None)
            )
            story_epic_id = (
                story.get("epic_id")
                if hasattr(story, "get")
                else getattr(story, "epic_id", None)
            )
            
            if not story_id or story_id in rag_context or (story_feature_id and story_feature_id in rag_context):
                continue

            feature = feature_lookup.get(story_feature_id)
            if not feature:
                continue
            epic = epic_lookup.get(story_epic_id) if story_epic_id else None
            
            epic_name = (
                epic.get("name")
                if hasattr(epic, "get")
                else getattr(epic, "name", None)
            ) or ""
            feature_name = (
                feature.get("name")
                if hasattr(feature, "get")
                else getattr(feature, "name", None)
            ) or ""
            requirement_ids = (
                story.get("requirement_refs")
                if hasattr(story, "get")
                else getattr(story, "requirement_refs", None)
            ) or []

            try:
                t0 = time.perf_counter()
                hybrid_result = await hybrid.retrieve(
                    epic=epic_name,
                    feature=feature_name,
                    requirement_ids=requirement_ids,
                    project_id=str(project_id) if project_id else None,
                    document_id=str(document_id) if document_id else None,
                    bm25_top_k=20,
                    dense_top_k=20,
                )

                fused = rrf.fuse(hybrid_result.bm25_results, hybrid_result.dense_results)
                query_str = f"{epic_name} {feature_name}".strip()
                reranked = await reranker.rerank(
                    query_str,
                    fused,
                    candidate_count=min(len(fused), 20),
                    final_count=5,
                )
                pipeline_ms = (time.perf_counter() - t0) * 1000

                context_package = cb.build_context_package(
                    epic=epic_name,
                    feature=feature_name,
                    reranked_chunks=reranked,
                    requirement_ids=requirement_ids,
                    retrieval_metadata={
                        "bm25_latency_ms": hybrid_result.bm25_latency_ms,
                        "dense_latency_ms": hybrid_result.dense_latency_ms,
                        "pipeline_latency_ms": pipeline_ms,
                        "bm25_count": len(hybrid_result.bm25_results),
                        "dense_count": len(hybrid_result.dense_results),
                        "fused_count": len(fused),
                        "reranked_count": len(reranked),
                    },
                )

                pkg_dict = context_package.model_dump()
                rag_context[story_id] = pkg_dict
                rag_context[story_feature_id] = pkg_dict

                all_chunks.extend(pkg_dict.get("source_chunks") or [])
                all_business_rules.extend(pkg_dict.get("business_rules") or [])
                all_dependencies.extend(pkg_dict.get("dependencies") or [])
                all_requirements.extend(pkg_dict.get("supporting_requirements") or [])

            except Exception as exc:
                logger.warning("RAG context retrieval failed for story %s: %s. Continuing pipeline.", story_id, exc)
                continue

        if all_chunks:
            chunk_lookup = {}
            for c in all_chunks:
                cid = c.get("chunk_id") or c.get("id")
                if cid and cid not in chunk_lookup:
                    chunk_lookup[cid] = c
            rag_context["source_chunks"] = list(chunk_lookup.values())
            rag_context["business_rules"] = list(set(all_business_rules))
            rag_context["dependencies"] = list(set(all_dependencies))
            
            req_lookup = {}
            for r in all_requirements:
                rid = r.get("id")
                if rid and rid not in req_lookup:
                    req_lookup[rid] = r
            rag_context["supporting_requirements"] = list(req_lookup.values())

        traceability["rag_context"] = rag_context
        return {"traceability": traceability, "rag_context": rag_context}

    async def human_review_hook(self, state: WorkflowState) -> WorkflowState:
        return {
            "human_review": {
                **state.get("human_review", {}),
                "status": "not_configured",
            }
        }

    def _create_preprocessing_service(self) -> DocumentPreprocessingPipelineService:
        return DocumentPreprocessingPipelineService(
            importer=self.importer or DocumentImportService(),
            chunker=self.chunker or ChunkService(),
            context_labeler=self.context_labeler or ContextLabeler(),
            requirement_analyzer=DeferredRequirementAnalyzer(),
        )
