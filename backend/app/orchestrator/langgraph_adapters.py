from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.orchestrator.langgraph_state import WorkflowState
from app.schemas import Chunk, PreprocessingPipelineResponse
from app.schemas.user_story import (
    Agent1Output,
    Agent2Output,
    GenerateUserStoriesRequest,
    OneLineStoryInput,
    PlanningArtifact,
    RetrievedChunk,
    ValidateUserStoriesRequest,
)


class DeferredRequirementAnalyzer:
    """No-op analyzer used when LangGraph runs requirement analysis in its own node."""

    async def run(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        return {}


@dataclass(slots=True)
class WorkflowStateAdapter:
    """Maps service and agent outputs into WorkflowState updates."""

    def preprocessing_response_to_state(
        self,
        response: PreprocessingPipelineResponse,
        *,
        document_id: UUID | str | None,
        project_id: UUID | str | None,
    ) -> WorkflowState:
        labeled_chunks = response.labeled_chunks
        resolved_document_id = document_id
        resolved_project_id = project_id
        if labeled_chunks:
            # Preprocessing resolves user-facing slugs to stable UUIDs. Use
            # those UUIDs for database/vector filters instead of preserving a
            # slug such as "cd", which PostgreSQL cannot cast to uuid.
            resolved_document_id = labeled_chunks[0].document_id
            resolved_project_id = labeled_chunks[0].project_id
        return {
            "document_id": resolved_document_id,
            "project_id": resolved_project_id,
            "parsed_text": response.parsed_text,
            "chunks": response.chunks,
            "labeled_chunks": labeled_chunks,
            "retrieved_chunks": [
                self.chunk_to_retrieved_chunk(chunk) for chunk in labeled_chunks
            ],
            "requirement_chunks": [self.chunk_to_dict(chunk) for chunk in labeled_chunks],
        }

    def requirement_analysis_to_state(
        self,
        output: Any,
        *,
        retrieved_chunks: list[RetrievedChunk],
    ) -> WorkflowState:
        requirement_analysis = self.dump_model(output)
        agent1_output = self.agent1_output_from_analysis(
            requirement_analysis=requirement_analysis,
            retrieved_chunks=retrieved_chunks,
        )
        return {
            "requirement_analysis": requirement_analysis,
            "agent1_output": agent1_output,
            "retrieved_chunks": agent1_output.chunks,
        }

    def epic_generation_to_state(self, output: Any) -> WorkflowState:
        return {
            "epic_generation": output,
            "epics": [
                PlanningArtifact(
                    id=epic.epic_id,
                    name=epic.title,
                    metadata={
                        "priority": epic.priority,
                        "dependencies": epic.dependencies,
                        "features": epic.features,
                        "one_line_story": epic.one_line_story,
                    },
                )
                for epic in output.epics
            ],
        }

    def one_line_stories_to_state(
        self,
        one_line_stories: list[OneLineStoryInput],
        *,
        epics: list[PlanningArtifact],
        features: list[PlanningArtifact],
        retrieved_chunks: list[RetrievedChunk],
        agent1_output: Agent1Output | None,
        traceability: dict[str, Any],
    ) -> WorkflowState:
        traceability_matrix = self.build_traceability_matrix(
            one_line_stories=one_line_stories,
            retrieved_chunks=retrieved_chunks,
            requirements=(agent1_output or Agent1Output()).functional_requirements,
        )
        agent2_output = Agent2Output(
            epics=epics,
            features=features,
            one_line_stories=one_line_stories,
            traceability_matrix=traceability_matrix,
            planning_metadata={
                "source": "langgraph_orchestration",
                "epic_generation_adapter": True,
            },
        )
        return {
            "one_line_stories": one_line_stories,
            "agent2_output": agent2_output,
            "traceability": {
                **traceability,
                "traceability_matrix": traceability_matrix,
            },
        }

    def story_request_to_state(self, request: GenerateUserStoriesRequest) -> WorkflowState:
        state: WorkflowState = {
            "workflow_id": request.workflow_id,
            "workflow_status": "RUNNING",
            "errors": [],
            "failed_node": None,
            "last_error": None,
            "current_node": "START",
            "completed_nodes": [],
            "failed_nodes": [],
            "retry_count": 0,
            "retry_reason": None,
            "retry_status": None,
            "retry_history": [],
            "review_required": False,
            "review_status": None,
            "approval_status": None,
            "execution_history": [],
            "workflow_progress": 0,
            "warnings": [],
            "node_execution_log": [],
            "audit_log": [],
            "execution_time": None,
            "confidence_threshold": getattr(request, "confidence_threshold", 0.8),
            "max_retry_attempts": getattr(request, "max_retry_attempts", 3),
            "retrieved_chunks": getattr(request, "retrieved_chunks", []),
            "requirement_chunks": [self.chunk_to_dict(chunk) for chunk in (getattr(request, "retrieved_chunks", []) or [])],
            "traceability": getattr(request, "traceability", {}),
        }
        if getattr(request, "agent1_output", None) is not None:
            state["agent1_output"] = request.agent1_output
        if getattr(request, "agent2_output", None) is not None:
            state["agent2_output"] = request.agent2_output
        if getattr(request, "epics", None):
            state["epics"] = request.epics
        if getattr(request, "features", None):
            state["features"] = request.features
        if getattr(request, "one_line_stories", None):
            state["one_line_stories"] = request.one_line_stories
        if getattr(request, "generated_user_stories", None):
            state["user_stories"] = request.generated_user_stories
        return state

    def generation_request_from_state(self, state: WorkflowState) -> GenerateUserStoriesRequest:
        retrieved_chunks = state.get("retrieved_chunks") or []
        agent1_output = state.get("agent1_output") or Agent1Output(chunks=retrieved_chunks)
        agent2_output = state.get("agent2_output") or Agent2Output(
            epics=state.get("epics", []),
            features=state.get("features", []),
            one_line_stories=state.get("one_line_stories", []),
        )
        return GenerateUserStoriesRequest(
            workflow_id=state.get("workflow_id", f"WF-{uuid4().hex[:8].upper()}"),
            confidence_threshold=state.get("confidence_threshold", 0.8),
            max_retry_attempts=state.get("max_retry_attempts", 3),
            retrieved_chunks=retrieved_chunks,
            agent1_output=agent1_output,
            agent2_output=agent2_output,
            traceability=state.get("traceability", {}),
        )

    def validation_request_from_state(self, state: WorkflowState) -> ValidateUserStoriesRequest:
        request = state.get("generation_request") or self.generation_request_from_state(state)
        if isinstance(request, dict):
            request = GenerateUserStoriesRequest(**request)
        traceability_matrix = self.build_traceability_matrix(
            one_line_stories=request.one_line_stories,
            retrieved_chunks=request.retrieved_chunks,
            requirements=request.requirements,
        )
        return ValidateUserStoriesRequest(
            workflow_id=request.workflow_id,
            generated_user_stories=state.get("user_stories", []),
            requirements=request.requirements,
            business_rules=request.business_rules,
            acceptance_criteria=request.acceptance_criteria,
            dependencies=request.dependencies,
            traceability={
                **request.traceability,
                # Rebuild from the authoritative planning artifacts so older
                # cached workflows also receive per-feature expanded rows.
                "traceability_matrix": traceability_matrix,
                "features": [feature.model_dump() for feature in request.features],
                "epics": [epic.model_dump() for epic in request.epics],
                "one_line_stories": [
                    story.model_dump() for story in request.one_line_stories
                ],
            },
            retrieved_chunks=request.retrieved_chunks,
            confidence_threshold=request.confidence_threshold,
        )

    def agent1_output_from_analysis(
        self,
        *,
        requirement_analysis: dict[str, Any],
        retrieved_chunks: list[RetrievedChunk],
    ) -> Agent1Output:
        return Agent1Output(
            chunks=retrieved_chunks,
            actors=list(requirement_analysis.get("actors", [])),
            functional_requirements=self.artifacts_from_strings(
                requirement_analysis.get("functional_requirements", []),
                prefix="FR",
                actor_mappings=requirement_analysis.get("actor_requirement_mappings", []),
            ),
            non_functional_requirements=self.artifacts_from_strings(
                requirement_analysis.get("non_functional_requirements", []),
                prefix="NFR",
            ),
            business_rules=list(requirement_analysis.get("constraints", [])),
            dependencies=list(requirement_analysis.get("dependencies", [])),
            acceptance_criteria=list(requirement_analysis.get("edge_cases", [])),
            traceability_metadata={
                "source": "requirement_analysis_agent",
                "business_goals": list(requirement_analysis.get("business_goals", [])),
                "actor_requirement_mappings": list(
                    requirement_analysis.get("actor_requirement_mappings", [])
                ),
            },
        )

    @staticmethod
    def artifacts_from_strings(
        values: list[str],
        *,
        prefix: str,
        actor_mappings: list[dict[str, Any]] | None = None,
    ) -> list[PlanningArtifact]:
        mappings = actor_mappings or []
        artifacts: list[PlanningArtifact] = []
        for index, value in enumerate(values, start=1):
            normalized_value = " ".join(value.casefold().split()).rstrip(".")
            mapping = next(
                (
                    item
                    for item in mappings
                    if isinstance(item, dict)
                    and " ".join(str(item.get("requirement", "")).casefold().split()).rstrip(".")
                    == normalized_value
                ),
                {},
            )
            artifacts.append(
                PlanningArtifact(
                    id=f"{prefix}-{index:03d}",
                    name=value,
                    metadata={
                        "actor": str(mapping.get("actor", "")).strip() or None,
                        "chunk_refs": list(mapping.get("chunk_refs") or []),
                    },
                )
            )
        return artifacts

    @staticmethod
    def build_traceability_matrix(
        *,
        one_line_stories: list[OneLineStoryInput],
        retrieved_chunks: list[RetrievedChunk],
        requirements: list[PlanningArtifact],
    ) -> list[dict[str, Any]]:
        chunk_ids = [chunk.id for chunk in retrieved_chunks]
        rows: list[dict[str, Any]] = []
        seen_mappings: set[tuple[str, str]] = set()
        for story in one_line_stories:
            feature_ids = story.feature_refs or [story.feature_id]
            for feature_id in feature_ids:
                mapping = (feature_id, story.id)
                if mapping in seen_mappings:
                    continue
                seen_mappings.add(mapping)
                rows.append(
                    {
                        "feature_id": feature_id,
                        "one_line_story_id": story.id,
                        "epic_id": story.epic_id,
                        "chunk_ids": story.chunk_refs or chunk_ids,
                        "requirement_ids": list(story.requirement_refs),
                        "actor": story.actor,
                    }
                )
        return rows

    @staticmethod
    def chunk_to_retrieved_chunk(chunk: Chunk) -> RetrievedChunk:
        return RetrievedChunk(
            id=str(chunk.id),
            content=chunk.content,
            source=str(chunk.metadata.get("source", "")) or None,
            metadata=WorkflowStateAdapter.json_safe(chunk.metadata),
        )

    @staticmethod
    def chunk_to_dict(chunk: Any) -> dict[str, Any]:
        from datetime import datetime, timezone
        metadata = getattr(chunk, "metadata", {}) or {}
        
        doc_id = getattr(chunk, "document_id", None)
        if doc_id is None:
            doc_id = metadata.get("document_id") or metadata.get("documentId")
            
        proj_id = getattr(chunk, "project_id", None)
        if proj_id is None:
            proj_id = metadata.get("project_id") or metadata.get("projectId")
            
        created_at = getattr(chunk, "created_at", None)
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        elif isinstance(created_at, str):
            created_at_str = created_at
        else:
            created_at_str = datetime.now(timezone.utc).isoformat()
            
        return {
            "chunk_id": str(getattr(chunk, "id", "")),
            "document_id": str(doc_id) if doc_id is not None else None,
            "project_id": str(proj_id) if proj_id is not None else None,
            "chunk_index": getattr(chunk, "chunk_index", 0),
            "section_title": getattr(chunk, "section_title", None),
            "content": getattr(chunk, "content", ""),
            "token_count": getattr(chunk, "token_count", 0),
            "context": getattr(chunk, "context", None),
            "content_hash": getattr(chunk, "content_hash", None),
            "metadata": WorkflowStateAdapter.json_safe(metadata),
            "created_at": created_at_str,
        }

    @staticmethod
    def dump_model(value: Any) -> dict[str, Any]:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        return dict(value)

    @staticmethod
    def json_safe(value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, dict):
            return {
                str(key): WorkflowStateAdapter.json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [WorkflowStateAdapter.json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [WorkflowStateAdapter.json_safe(item) for item in value]
        return value


class EpicFeatureAdapter:
    """Default Feature adapter using the existing Epic Generation output."""

    async def execute(self, state: WorkflowState) -> list[PlanningArtifact]:
        features: list[PlanningArtifact] = []
        for epic in getattr(state.get("epic_generation"), "epics", []):
            for index, feature_name in enumerate(epic.features, start=1):
                features.append(
                    PlanningArtifact(
                        id=f"{epic.epic_id}-FEAT-{index:03d}",
                        name=feature_name,
                        metadata={
                            "epic_id": epic.epic_id,
                            "source": "epic_generation.features",
                            "actor": epic.feature_actors.get(feature_name),
                        },
                    )
                )
        return features


class EpicOneLineStoryAdapter:
    """Default One-Line Story adapter using the existing Epic Generation output."""

    async def execute(self, state: WorkflowState) -> list[OneLineStoryInput]:
        stories: list[OneLineStoryInput] = []
        features_by_epic: dict[str, list[PlanningArtifact]] = {}
        for feature in state.get("features", []):
            epic_id = str(feature.metadata.get("epic_id", ""))
            features_by_epic.setdefault(epic_id, []).append(feature)

        agent1_output = state.get("agent1_output") or Agent1Output()

        for epic in getattr(state.get("epic_generation"), "epics", []):
            epic_features = features_by_epic.get(epic.epic_id, [])
            for index, feature in enumerate(epic_features, start=1):
                actor = str(feature.metadata.get("actor") or "").strip() or None
                actor_parts = {
                    part.casefold()
                    for part in re.split(r"\s*(?:,|/|\band\b)\s*", actor or "")
                    if part.strip()
                }
                actor_requirements = [
                    requirement
                    for requirement in agent1_output.functional_requirements
                    if actor
                    and str(requirement.metadata.get("actor") or "").casefold()
                    in actor_parts
                ]
                feature_tokens = self.meaningful_tokens(feature.name or feature.id)
                scoped_requirements = [
                    requirement
                    for requirement in actor_requirements
                    if feature_tokens.intersection(
                        self.meaningful_tokens(requirement.name or requirement.id)
                    )
                ]
                requirement_refs = [requirement.id for requirement in scoped_requirements]
                chunk_refs = list(
                    dict.fromkeys(
                        ref
                        for requirement in scoped_requirements
                        for ref in requirement.metadata.get("chunk_refs", [])
                    )
                )
                if not chunk_refs:
                    chunk_refs = [chunk.id for chunk in state.get("retrieved_chunks", [])]
                goal = feature.name or feature.id
                business_value = self.business_value_from_story(epic.one_line_story)
                summary = (
                    f"As a {actor}, I want to {goal}, so that {business_value}."
                    if actor and business_value
                    else goal
                )
                stories.append(
                    OneLineStoryInput(
                        id=f"{epic.epic_id}-STORY-{index:03d}",
                        feature_id=feature.id,
                        feature_refs=[feature.id],
                        epic_id=epic.epic_id,
                        summary=summary,
                        actor=actor,
                        business_value=business_value,
                        requirement_refs=requirement_refs,
                        chunk_refs=chunk_refs,
                        dependency_refs=list(epic.dependencies),
                    )
                )
        return stories

    @staticmethod
    def meaningful_tokens(value: str) -> set[str]:
        stop_words = {
            "and", "for", "the", "with", "management", "functionality", "system",
        }
        return {
            token for token in re.findall(r"[a-z0-9]+", value.casefold())
            if len(token) > 2 and token not in stop_words
        }

    @staticmethod
    def business_value_from_story(story: str) -> str | None:
        marker = " so that "
        lower_story = story.lower()
        if marker not in lower_story:
            return None
        start = lower_story.index(marker) + len(marker)
        return story[start:].strip().rstrip(".")
