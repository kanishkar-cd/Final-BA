from __future__ import annotations

import json
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.shared_intelligence import (
    ConfidenceCalculator,
    EvidencePack,
    EvidencePackBuilder,
    MetadataFactory,
    QualityGates,
    SharedValidators,
    dedupe_strings,
    source_chunk_references as build_source_chunk_references,
)
from app.agents.token_budget import TokenBudgetManager, count_tokens
from app.prompts.prompt_manager import PromptManager
from app.schemas.user_story import (
    AcceptanceCriterion,
    Agent1Output,
    Agent2Output,
    GenerateUserStoriesRequest,
    InvestCompliance,
    MappingReference,
    OneLineStoryInput,
    PlanningArtifact,
    RetrievedChunk,
    StoryDependency,
    UserStory,
    TraceabilityLink,
)
from app.traceability.traceability_service import TraceabilityService
from app.utils.logger import get_logger
from app.shared.llm_client import LLMService, LLMServiceError


AgentExecutor = Callable[[str, str, GenerateUserStoriesRequest], Awaitable[list[UserStory]]]


class UserStoriesOutput(BaseModel):
    """Structured output returned by the LLM containing generated user stories."""
    user_stories: list[UserStory] = Field(default_factory=list)
    traceability_links: list[TraceabilityLink] = Field(default_factory=list)
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 1.0


class UserStoryGenerationAgent(BaseAgent[GenerateUserStoriesRequest, list[UserStory]]):
    """Agent 3: evidence-grounded generator for production Agile user stories."""

    def __init__(
        self,
        prompt_manager: PromptManager | None = None,
        traceability_service: TraceabilityService | None = None,
        agent_executor: AgentExecutor | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        super().__init__("agent-3-user-story-generator")
        self._prompt_manager = prompt_manager or PromptManager()
        self._traceability_service = traceability_service or TraceabilityService()
        self._agent_executor = agent_executor
        self.llm_service = llm_service or LLMService(self._prompt_manager)
        self._logger = get_logger(__name__)

    async def execute(self, payload: GenerateUserStoriesRequest) -> list[UserStory]:
        evidence_packs = EvidencePackBuilder(payload).build()
        self._logger.info("Generating user stories for workflow=%s", payload.workflow_id)
        batches = self._build_batches(payload, evidence_packs)
        generated: list[UserStory] = []
        for batch_index, batch in enumerate(batches, start=1):
            generated.extend(await self._execute_batch(
                payload, batch, batch_index=batch_index, split_depth=0
            ))
        return _dedupe_stories(generated, logger=self._logger)

    async def _execute_batch(
        self,
        payload: GenerateUserStoriesRequest,
        evidence_packs: list[EvidencePack],
        *,
        batch_index: int,
        split_depth: int,
    ) -> list[UserStory]:
        scoped_payload = self._scoped_payload(payload, evidence_packs)
        prompt = self._prompt_manager.get_user_story_batch_prompt(
            self._batch_context(evidence_packs),
            self._story_schema(),
        )
        estimated_input_tokens = count_tokens(prompt.system_prompt) + count_tokens(prompt.user_prompt)
        output_tokens = self._output_token_allowance(len(evidence_packs))
        try:
            if self._agent_executor is not None:
                raw_stories = await self._agent_executor(
                    prompt.system_prompt, prompt.user_prompt, scoped_payload
                )
                output = UserStoriesOutput(user_stories=raw_stories)
            else:
                output = await self.llm_service.execute(
                    prompt=prompt.user_prompt,
                    system_prompt=prompt.system_prompt,
                    response_schema=UserStoriesOutput,
                    prompt_version="v1",
                    max_tokens=output_tokens,
                )
            if isinstance(output, UserStoriesOutput) and output.user_stories:
                return self._quality_gate_or_fallback(
                    scoped_payload,
                    evidence_packs,
                    output.user_stories,
                    generation_metadata={
                        **output.generation_metadata,
                        "batch_index": batch_index,
                        "batch_size": len(evidence_packs),
                        "split_depth": split_depth,
                        "estimated_input_tokens": estimated_input_tokens,
                        "max_output_tokens": output_tokens,
                    },
                    aggregate_confidence=output.confidence_score,
                )
            self._logger.warning(
                "User story generation provider returned no stories. Returning failure records."
            )
            return self._generation_failed_stories(evidence_packs, "empty_provider_output")
        except Exception as exc:
            if _is_too_large_request(exc) and len(evidence_packs) > 1:
                midpoint = max(1, len(evidence_packs) // 2)
                self._logger.warning(
                    "User story batch %s exceeded the provider request limit; splitting %s stories into %s and %s.",
                    batch_index, len(evidence_packs), midpoint, len(evidence_packs) - midpoint,
                )
                left = await self._execute_batch(
                    payload, evidence_packs[:midpoint],
                    batch_index=batch_index, split_depth=split_depth + 1,
                )
                right = await self._execute_batch(
                    payload, evidence_packs[midpoint:],
                    batch_index=batch_index, split_depth=split_depth + 1,
                )
                return [*left, *right]
            self._logger.warning(
                "LLM user story generation failed: %s. Returning failure records.",
                exc.__class__.__name__,
                exc_info=True,
            )
            return self._generation_failed_stories(evidence_packs, exc.__class__.__name__)

    def _build_batches(
        self,
        payload: GenerateUserStoriesRequest,
        evidence_packs: list[EvidencePack],
    ) -> list[list[EvidencePack]]:
        budget = self._batch_token_budget()
        max_stories = max(1, int(os.getenv("USER_STORY_BATCH_MAX_STORIES", "3")))
        batches: list[list[EvidencePack]] = []
        current: list[EvidencePack] = []
        for pack in evidence_packs:
            candidate = [*current, pack]
            prompt = self._prompt_manager.get_user_story_batch_prompt(
                self._batch_context(candidate),
                self._story_schema(),
            )
            estimated_total = (
                count_tokens(prompt.system_prompt)
                + count_tokens(prompt.user_prompt)
                + self._output_token_allowance(len(candidate))
            )
            if current and (estimated_total > budget or len(candidate) > max_stories):
                batches.append(current)
                current = [pack]
            else:
                current = candidate
        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _output_token_allowance(story_count: int) -> int:
        per_story = max(500, int(os.getenv("USER_STORY_OUTPUT_TOKENS_PER_STORY", "2800")))
        minimum = max(500, int(os.getenv("USER_STORY_MIN_OUTPUT_TOKENS", "2800")))
        return min(8192, max(minimum, story_count * per_story))

    @staticmethod
    def _batch_token_budget() -> int:
        configured = os.getenv("USER_STORY_BATCH_TOKEN_BUDGET")
        if configured:
            return max(1000, int(configured))
        return TokenBudgetManager(
            os.getenv("MODEL_PROVIDER", "openai"),
            os.getenv("MODEL_NAME", "gpt-4o"),
        ).ceiling

    @staticmethod
    def _batch_context(evidence_packs: list[EvidencePack]) -> str:
        context = []
        for pack in evidence_packs:
            context.append({
                "story_id": pack.story_id,
                "epic": pack.epic.model_dump(mode="json"),
                "feature": pack.feature.model_dump(mode="json"),
                "one_line_story": pack.one_line_story.model_dump(mode="json"),
                "actor": pack.actor,
                "business_value": pack.business_value,
                "chunks": [chunk.model_dump(mode="json") for chunk in pack.retrieved_chunks],
                "requirements": [item.model_dump(mode="json") for item in pack.requirements],
                "non_functional_requirements": [
                    item.model_dump(mode="json") for item in pack.non_functional_requirements
                ],
                "business_rules": pack.business_rules,
                "source_acceptance_criteria": pack.acceptance_criteria,
                "dependencies": pack.dependencies,
                "business_goals": pack.business_goals,
                "chunk_refs": pack.chunk_refs,
                "requirement_refs": pack.requirement_refs,
                "traceability_rows": pack.traceability_rows,
                "story_context": pack.story_context,
                "rag_context": pack.rag_context,
            })
        return json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _story_schema() -> str:
        return json.dumps(
            UserStory.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _scoped_payload(
        payload: GenerateUserStoriesRequest,
        evidence_packs: list[EvidencePack],
    ) -> GenerateUserStoriesRequest:
        chunks = list({item.id: item for pack in evidence_packs for item in pack.retrieved_chunks}.values())
        requirements = list({item.id: item for pack in evidence_packs for item in pack.requirements}.values())
        nfrs = list({item.id: item for pack in evidence_packs for item in pack.non_functional_requirements}.values())
        epics = list({pack.epic.id: pack.epic for pack in evidence_packs}.values())
        features = list({pack.feature.id: pack.feature for pack in evidence_packs}.values())
        stories = list({pack.one_line_story.id: pack.one_line_story for pack in evidence_packs}.values())
        actors = dedupe_strings([item for pack in evidence_packs for item in pack.actors])
        rules = dedupe_strings([item for pack in evidence_packs for item in pack.business_rules])
        criteria = dedupe_strings([item for pack in evidence_packs for item in pack.acceptance_criteria])
        dependencies = dedupe_strings([item for pack in evidence_packs for item in pack.dependencies])
        goals = dedupe_strings([item for pack in evidence_packs for item in pack.business_goals])
        feature_ids = {pack.feature.id for pack in evidence_packs}
        one_line_ids = {pack.one_line_story.id for pack in evidence_packs}
        rows = [
            row for row in payload.traceability.get("traceability_matrix", [])
            if isinstance(row, dict)
            and (row.get("feature_id") in feature_ids or row.get("one_line_story_id") in one_line_ids)
        ]
        if not rows:
            rows = [row for pack in evidence_packs for row in pack.traceability_rows]
        traceability = {
            "traceability_matrix": rows,
            "actor_requirement_mappings": payload.traceability.get("actor_requirement_mappings", []),
            "story_context": payload.traceability.get("story_context", {}),
            "master_context": payload.traceability.get("master_context", {}),
        }
        agent1_metadata = dict(
            payload.agent1_output.traceability_metadata if payload.agent1_output else {}
        )
        agent1_metadata["business_goals"] = goals
        agent1 = Agent1Output(
            chunks=chunks,
            actors=actors,
            functional_requirements=requirements,
            non_functional_requirements=nfrs,
            business_rules=rules,
            dependencies=dependencies,
            acceptance_criteria=criteria,
            traceability_metadata=agent1_metadata,
        )
        agent2 = Agent2Output(
            epics=epics,
            features=features,
            one_line_stories=stories,
            traceability_matrix=rows,
            planning_metadata=(
                payload.agent2_output.planning_metadata if payload.agent2_output else {}
            ),
        )
        return payload.model_copy(update={
            "retrieved_chunks": chunks,
            "actors": actors,
            "functional_requirements": requirements,
            "requirements": requirements,
            "non_functional_requirements": nfrs,
            "business_rules": rules,
            "acceptance_criteria": criteria,
            "dependencies": dependencies,
            "business_goals": goals,
            "epics": epics,
            "features": features,
            "one_line_stories": stories,
            "agent1_output": agent1,
            "agent2_output": agent2,
            "traceability": traceability,
        })

    async def regenerate_failed_stories(
        self,
        payload: GenerateUserStoriesRequest,
        previous_stories: list[UserStory],
        failed_story_ids: list[str],
    ) -> list[UserStory]:
        if not failed_story_ids:
            return previous_stories

        failed_stories = [story for story in previous_stories if story.id in failed_story_ids]
        failed_feature_ids = {story.feature_id for story in failed_stories}
        scoped_one_line_stories: list[OneLineStoryInput] = []
        for planning_story in payload.one_line_stories:
            linked_features = set(planning_story.feature_refs or [planning_story.feature_id])
            for feature_id in sorted(linked_features & failed_feature_ids):
                scoped_one_line_stories.append(
                    planning_story.model_copy(
                        update={
                            "feature_id": feature_id,
                            "feature_refs": [feature_id],
                        }
                    )
                )
        scoped_epic_ids = {
            story.epic_id for story in scoped_one_line_stories if story.epic_id
        } | {story.epic_id for story in failed_stories if story.epic_id}
        scoped_epics = [epic for epic in payload.epics if epic.id in scoped_epic_ids]
        scoped_features = [
            feature for feature in payload.features if feature.id in failed_feature_ids
        ]
        scoped_story_ids = {story.id for story in scoped_one_line_stories}
        scoped_matrix = [
            row
            for row in payload.traceability.get("traceability_matrix", [])
            if not isinstance(row, dict)
            or (
                (row.get("feature_id") in failed_feature_ids)
                or (row.get("one_line_story_id") in scoped_story_ids)
            )
        ]
        selected_chunk_refs = {
            ref for story in scoped_one_line_stories for ref in story.chunk_refs
        }
        selected_requirement_refs = {
            ref for story in scoped_one_line_stories for ref in story.requirement_refs
        }
        for row in scoped_matrix:
            if not isinstance(row, dict):
                continue
            selected_chunk_refs.update(
                str(ref) for ref in (row.get("chunk_ids") or row.get("chunk_refs") or [])
            )
            selected_requirement_refs.update(
                str(ref) for ref in (row.get("requirement_ids") or row.get("requirement_refs") or [])
            )
        scoped_chunks = [
            chunk for chunk in payload.retrieved_chunks if chunk.id in selected_chunk_refs
        ]
        scoped_requirements = [
            requirement
            for requirement in payload.functional_requirements
            if requirement.id in selected_requirement_refs
        ]
        scoped_traceability = {
            "traceability_matrix": scoped_matrix,
            "planning_metadata": payload.traceability.get("planning_metadata", {}),
            "regeneration_feedback": payload.traceability.get("regeneration_feedback", ""),
        }
        scoped_agent1 = Agent1Output(
            chunks=scoped_chunks,
            actors=list(payload.actors),
            functional_requirements=scoped_requirements,
            non_functional_requirements=[],
            business_rules=list(payload.business_rules),
            dependencies=list(payload.dependencies),
            acceptance_criteria=list(payload.acceptance_criteria),
            traceability_metadata={
                "business_goals": list(payload.business_goals[:2]),
            },
        )
        scoped_agent2 = Agent2Output(
            epics=scoped_epics,
            features=scoped_features,
            one_line_stories=scoped_one_line_stories,
            traceability_matrix=scoped_matrix,
            planning_metadata=(
                payload.agent2_output.planning_metadata
                if payload.agent2_output is not None
                else {}
            ),
        )
        scoped_payload = payload.model_copy(
            update={
                "epics": scoped_epics,
                "features": scoped_features,
                "one_line_stories": scoped_one_line_stories,
                "retrieved_chunks": scoped_chunks,
                "requirements": scoped_requirements,
                "functional_requirements": scoped_requirements,
                "non_functional_requirements": [],
                "agent1_output": scoped_agent1,
                "agent2_output": scoped_agent2,
                "traceability": scoped_traceability,
            }
        )

        # Interactive regeneration must return within the HTTP request window.
        # Reuse the evidence-grounded deterministic generator instead of
        # waiting on provider throttling/retries for a single selected story.
        regenerated = self._generate_deterministic_stories(scoped_payload)
        regenerated_by_feature = {story.feature_id: story for story in regenerated}
        merged: list[UserStory] = []
        for story in previous_stories:
            if story.id in failed_story_ids and story.retry_attempts < payload.max_retry_attempts:
                replacement = regenerated_by_feature.get(story.feature_id)
                if replacement is not None:
                    replacement.id = story.id
                    replacement.retry_attempts = story.retry_attempts + 1
                    replacement.traceability.metadata["regenerated_from_story_id"] = story.id
                    replacement.traceability.metadata["regeneration_attempt"] = replacement.retry_attempts
                    merged.append(replacement)
                    continue
            merged.append(story)
        return merged

    def _generate_deterministic_stories(
        self,
        payload: GenerateUserStoriesRequest,
        *,
        evidence_packs: list[EvidencePack] | None = None,
    ) -> list[UserStory]:
        packs = evidence_packs or EvidencePackBuilder(payload).build()
        stories: list[UserStory] = []
        seen_story_keys: set[tuple[str, str]] = set()
        for pack in packs:
            story_key = (pack.feature.id, pack.one_line_story.id)
            if story_key in seen_story_keys:
                self._logger.warning(
                    "Skipping duplicate feature/story mapping '%s' (%s).",
                    pack.one_line_story.id,
                    pack.feature.id,
                )
                continue
            seen_story_keys.add(story_key)
            stories.append(self._generate_story_from_pack(pack, existing_stories=stories))
        return stories

    def _generation_failed_stories(
        self,
        evidence_packs: list[EvidencePack],
        failure_type: str,
    ) -> list[UserStory]:
        """Return identity-only records so validation can retry or request review."""
        failed_stories: list[UserStory] = []
        for pack in evidence_packs:
            traceability = self._traceability_service.build_story_traceability(
                workflow_id=pack.workflow_id,
                one_line_story=pack.one_line_story,
                requirements=pack.requirements,
                epics=[pack.epic],
                features=[pack.feature],
                generated_by=self.name,
            )
            traceability.chunk_refs = pack.chunk_refs
            traceability.requirement_refs = (
                pack.requirement_refs or traceability.requirement_refs
            )
            traceability.metadata["generation_status"] = "FAILED"
            failed_stories.append(
                UserStory(
                    id=pack.story_id,
                    feature_id=pack.feature.id,
                    epic_id=pack.epic.id,
                    one_line_story_id=pack.one_line_story.id,
                    chunk_ids_used=pack.chunk_refs,
                    title=_title_from_summary(
                        pack.feature.name or pack.one_line_story.summary
                    ),
                    user_story="",
                    description="",
                    persona=pack.actor,
                    goal=_clean_goal(
                        pack.feature.name or pack.one_line_story.summary
                    ),
                    acceptance_criteria=[],
                    definition_of_done=[],
                    confidence_score=0.0,
                    traceability=traceability,
                    traceability_links={
                        "chunk_ids": pack.chunk_refs,
                        "requirement_ids": pack.requirement_refs,
                        "feature_id": pack.feature.id,
                        "epic_id": pack.epic.id,
                        "story_id": pack.story_id,
                        "one_line_story_id": pack.one_line_story.id,
                    },
                    metadata={
                        "source": "agent3_user_story_generation",
                        "generation_status": "FAILED",
                        "generation_failure_type": failure_type,
                        "fallback_content_generated": False,
                    },
                )
            )
        return failed_stories

    def _generate_story_from_pack(
        self,
        pack: EvidencePack,
        *,
        existing_stories: list[UserStory],
    ) -> UserStory:
        actor = pack.actor
        goal = _clean_goal(pack.feature.name or pack.one_line_story.summary)
        value = pack.business_value
        traceability = self._traceability_service.build_story_traceability(
            workflow_id=pack.workflow_id,
            one_line_story=pack.one_line_story,
            requirements=pack.requirements,
            epics=[pack.epic],
            features=[pack.feature],
            generated_by=self.name,
        )
        traceability.chunk_refs = pack.chunk_refs
        traceability.requirement_refs = pack.requirement_refs or traceability.requirement_refs
        traceability.metadata.update(
            {
                "source_of_truth": "agent1_output",
                "planning_context": "agent2_output",
                "generation_hierarchy": "Epic -> Feature -> One-Line Story -> Evidence Pack -> User Story",
                "feature_id": pack.feature.id,
                "epic_id": pack.epic.id,
                "one_line_story_id": pack.one_line_story.id,
                "traceability_rows": pack.traceability_rows,
                "planner_metadata": pack.planner_metadata,
                "master_context": pack.master_context,
                "story_context": pack.story_context,
                "rag_context_present": bool(pack.rag_context),
            }
        )
        acceptance_criteria = _build_acceptance_criteria(
            actor=actor,
            goal=goal,
            feature_name=pack.feature.name or pack.feature.id,
            source_criteria=pack.acceptance_criteria,
            relevant_chunks=pack.retrieved_chunks,
        )
        dependencies = _build_dependencies(
            pack.sequence,
            existing_stories,
            pack.dependencies,
            pack.one_line_story.dependency_refs,
            pack.retrieved_chunks,
        )
        source_chunk_references = build_source_chunk_references(pack.retrieved_chunks)
        confidence = ConfidenceCalculator.generation_confidence(
            pack=pack,
            acceptance_criteria=acceptance_criteria,
            dependencies=dependencies,
        ).to_dict()
        story = UserStory(
            id=pack.story_id,
            epic_id=pack.epic.id,
            feature_id=pack.feature.id,
            one_line_story_id=pack.one_line_story.id,
            chunk_ids_used=pack.chunk_refs,
            title=_title_from_summary(pack.feature.name or pack.one_line_story.summary),
            user_story=f"As a {actor}, I want to {goal}, so that {value}.",
            description=_description_for(
                goal=goal,
                epic_name=pack.epic.name,
                feature_name=pack.feature.name,
                business_goals=pack.business_goals,
                story_context=pack.story_context,
                master_context=pack.master_context,
                relevant_chunks=pack.retrieved_chunks,
            ),
            persona=actor,
            goal=goal,
            business_value=value,
            acceptance_criteria=acceptance_criteria,
            business_rules=_dedupe_explicit_rules(pack.business_rules),
            dependencies=dependencies,
            definition_of_done=_definition_of_done(acceptance_criteria),
            assumptions=MetadataFactory.assumptions_for_pack(pack),
            risks=_risks_from(pack.dependencies, pack.non_functional_requirements),
            requirement_mapping=[
                MappingReference(id=requirement.id, name=requirement.name, source=requirement.description)
                for requirement in pack.requirements
            ],
            epic_mapping=[
                MappingReference(id=pack.epic.id, name=pack.epic.name, source=pack.epic.description)
            ],
            feature_mapping=[
                MappingReference(id=pack.feature.id, name=pack.feature.name, source=pack.feature.description)
            ],
            source_chunk_references=source_chunk_references,
            priority=pack.one_line_story.priority,
            story_points=_estimate_points(pack),
            confidence_score=confidence["score"],
            invest_compliance=InvestCompliance(),
            traceability=traceability,
            traceability_links={
                "chunk_ids": pack.chunk_refs,
                "requirement_ids": pack.requirement_refs,
                "feature_id": pack.feature.id,
                "epic_id": pack.epic.id,
                "story_id": pack.story_id,
                "one_line_story_id": pack.one_line_story.id,
                "evidence_pack_id": MetadataFactory.evidence_pack_id(pack),
            },
            metadata={
                "source": "agent3_user_story_generation",
                "authoritative_source": "agent1_output",
                "planning_source": "agent2_output",
                "generation_hierarchy": "Epic -> Feature -> One-Line Story -> Evidence Pack -> User Story",
                "evidence_pack": MetadataFactory.evidence_pack_metadata(pack),
                "quality_gates": QualityGates.generation_report(pack, acceptance_criteria),
                "confidence": confidence,
                "one_line_story": pack.one_line_story.summary,
                "retrieved_chunk_ids": pack.chunk_refs,
                "retrieved_chunk_sources": [
                    chunk.source for chunk in pack.retrieved_chunks if chunk.source
                ],
            },
        )
        SharedValidators.validate_story_against_pack(story, pack)
        return story

    def _quality_gate_or_fallback(
        self,
        payload: GenerateUserStoriesRequest,
        evidence_packs: list[EvidencePack],
        stories: list[UserStory],
        *,
        generation_metadata: dict[str, Any] | None = None,
        aggregate_confidence: float | None = None,
    ) -> list[UserStory]:
        pack_lookup = {
            (pack.feature.id, pack.one_line_story.id): pack
            for pack in evidence_packs
        }
        if len(stories) != len(evidence_packs):
            self._logger.warning(
                "Agent 3 quality gate rejected LLM output: expected %s stories, got %s.",
                len(evidence_packs),
                len(stories),
            )
            return self._generation_failed_stories(
                evidence_packs,
                "invalid_story_count",
            )

        gated_stories: list[UserStory] = []
        try:
            for story in stories:
                key = (story.feature_id, story.one_line_story_id or "")
                pack = pack_lookup.get(key)
                if pack is None:
                    raise ValueError(
                        f"Generated story '{story.id}' does not map to an Evidence Pack"
                    )
                SharedValidators.validate_story_against_pack(story, pack)
                story.id = pack.story_id
                story.persona = pack.actor
                story.goal = _clean_goal(pack.feature.name or pack.one_line_story.summary)
                story.business_value = pack.business_value
                story.user_story = (
                    f"As a {story.persona}, I want to {story.goal}, "
                    f"so that {story.business_value}."
                )
                story.business_rules = _supported_business_rules(
                    story.business_rules,
                    pack.business_rules,
                )
                story.description = _description_for(
                    goal=story.goal,
                    epic_name=pack.epic.name,
                    feature_name=pack.feature.name,
                    business_goals=pack.business_goals,
                    story_context=pack.story_context,
                    master_context=pack.master_context,
                    relevant_chunks=pack.retrieved_chunks,
                )
                story.story_points = _estimate_points(pack)
                # The evidence-pack summary is the authoritative heading source.
                # It also prevents truncated or generic LLM-generated headings.
                story.title = _title_from_summary(pack.feature.name or pack.one_line_story.summary)
                confidence = ConfidenceCalculator.generation_confidence(
                    pack=pack,
                    acceptance_criteria=story.acceptance_criteria,
                    dependencies=story.dependencies,
                ).to_dict()
                if aggregate_confidence is not None:
                    confidence["llm_reported_confidence"] = aggregate_confidence
                story.confidence_score = confidence["score"]
                story.traceability.metadata.update(
                    {
                        "generation_hierarchy": "Epic -> Feature -> One-Line Story -> Evidence Pack -> User Story",
                        "evidence_pack_id": MetadataFactory.evidence_pack_id(pack),
                    }
                )
                story.metadata.update(
                    {
                        "source": "agent3_user_story_generation",
                        "generation_metadata": generation_metadata or {},
                        "evidence_pack": MetadataFactory.evidence_pack_metadata(pack),
                        "quality_gates": QualityGates.generation_report(pack, story.acceptance_criteria),
                        "confidence": confidence,
                    }
                )
                gated_stories.append(story)
        except ValueError as exc:
            self._logger.warning(
                "Agent 3 quality gate rejected LLM output: %s. Returning failure records.",
                exc,
            )
            return self._generation_failed_stories(
                evidence_packs,
                "quality_gate_rejected_output",
            )
        return _dedupe_stories(gated_stories, logger=self._logger)


def _first_or_default(values: list[str], default: str) -> str:
    return values[0] if values else default


def _is_too_large_request(exc: Exception) -> bool:
    message = str(exc).casefold()
    return any(marker in message for marker in (
        "request too large",
        "context length",
        "maximum context",
        "too many tokens",
        "requested tokens",
        "413",
    ))


def _clean_goal(summary: str) -> str:
    cleaned = summary.strip().rstrip(".")
    cleaned = re.sub(r"^(as an? .+?,\s*i want to\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(i want to\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^(develop|implement|create|build|code|configure)\s+",
        "provide ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned[:1].lower() + cleaned[1:] if cleaned else "complete the requested action"


def _title_from_summary(summary: str) -> str:
    title = " ".join(summary.strip().rstrip(".").split())
    title = re.sub(r"^as an? .+?,\s*i want to\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^i want to\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*,?\s*so that\s+.+$", "", title, flags=re.IGNORECASE)
    title = title or "Complete user action"
    return title[:1].upper() + title[1:]


def _normalized_text(value: str) -> str:
    """Return a stable comparison key for generated story text."""
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", value.lower()).split())


def _dedupe_explicit_rules(rules: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        cleaned = " ".join(rule.split())
        key = _normalized_text(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique


def _supported_business_rules(generated: list[str], supported: list[str]) -> list[str]:
    supported_by_key: dict[str, str] = {}
    for rule in supported:
        cleaned = " ".join(rule.split())
        if cleaned:
            supported_by_key.setdefault(_normalized_text(cleaned), cleaned)
    return [
        supported_by_key[key]
        for key in dict.fromkeys(_normalized_text(rule) for rule in generated)
        if key in supported_by_key
    ]


def _dedupe_stories(stories: list[UserStory], *, logger: Any) -> list[UserStory]:
    """Deduplicate only repeated source mappings, never distinct features."""
    unique: list[UserStory] = []
    seen_sources: set[tuple[str, str]] = set()
    for story in stories:
        source_key = (story.feature_id, story.one_line_story_id or "")
        if source_key in seen_sources:
            logger.warning("Skipping duplicate generated user story '%s'.", story.id)
            continue
        seen_sources.add(source_key)
        unique.append(story)
    return unique


def _derive_business_value(feature_name: str | None) -> str:
    if feature_name:
        return f"the {feature_name} capability delivers its intended business value"
    return "the business process can be completed successfully"


def _stories_by_feature(one_line_stories: list[OneLineStoryInput]) -> dict[str, OneLineStoryInput]:
    stories_by_feature: dict[str, OneLineStoryInput] = {}
    for story in one_line_stories:
        stories_by_feature.setdefault(story.feature_id, story)
    return stories_by_feature


def _generation_plan(payload: GenerateUserStoriesRequest) -> list[tuple[PlanningArtifact, OneLineStoryInput]]:
    feature_lookup = {feature.id: feature for feature in payload.features}
    if payload.agent2_output is not None:
        story_lookup = _stories_by_feature(payload.one_line_stories)
        plan: list[tuple[PlanningArtifact, OneLineStoryInput]] = []
        for feature in payload.features:
            one_line_story = story_lookup.get(feature.id)
            if one_line_story is None:
                raise ValueError(f"Feature '{feature.id}' must have a linked one-line story for Agent 3")
            plan.append((feature, one_line_story))
        return plan

    return [
        (
            feature_lookup.get(story.feature_id)
            or PlanningArtifact(id=story.feature_id, name=story.feature_id),
            story,
        )
        for story in payload.one_line_stories
    ]


def _description_for(
    *,
    goal: str,
    epic_name: str | None,
    feature_name: str | None,
    business_goals: list[str],
    story_context: dict[str, Any],
    master_context: dict[str, Any],
    relevant_chunks: list,
) -> str:
    epic_context = f" within {epic_name}" if epic_name else ""
    value_context = business_goals[0].strip().rstrip(".") if business_goals else "the intended business outcome"
    return (
        f"This work defines the expected user-facing behavior{epic_context}. "
        f"The implementation must enable {value_context}."
    )


def _build_acceptance_criteria(
    *,
    actor: str,
    goal: str,
    feature_name: str,
    source_criteria: list[str],
    relevant_chunks: list,
) -> list[AcceptanceCriterion]:
    chunk_refs = [chunk.id for chunk in relevant_chunks]
    criteria: list[AcceptanceCriterion] = []
    evidence_statements = _story_evidence_statements(relevant_chunks, source_criteria)
    for index, criterion in enumerate(evidence_statements[:5], start=1):
        criteria.append(
            AcceptanceCriterion(
                id=f"AC-{index:03d}",
                description=_as_given_when_then(
                    criterion,
                    feature_name,
                    actor=actor,
                    goal=goal,
                ),
                source_refs=[criterion, *chunk_refs],
            )
        )
    if not criteria:
        criteria.append(
            AcceptanceCriterion(
                id="AC-001",
                description=(
                    f"Given the documented prerequisites are satisfied, When the {actor} attempts "
                    f"to {goal.lower()}, Then the system must produce the observable outcome stated "
                    "in the mapped source requirement."
                ),
                source_refs=chunk_refs or ["generated-from-one-line-story"],
            )
        )
    return criteria[:5]


def _story_evidence_statements(
    relevant_chunks: list[RetrievedChunk],
    source_criteria: list[str],
) -> list[str]:
    """Return concrete, story-scoped statements before global criteria."""
    statements: list[str] = []
    for chunk in relevant_chunks:
        statements.extend(re.split(r"(?<=[.!?])\s+", chunk.content))
    statements.extend(source_criteria)
    return _dedupe_explicit_rules(
        [statement.strip() for statement in statements if len(statement.split()) >= 5]
    )


def _relevant_chunks_for_story(payload: GenerateUserStoriesRequest, chunk_refs: list[str]) -> list:
    chunks_by_id = {chunk.id: chunk for chunk in payload.retrieved_chunks}
    return [chunks_by_id[chunk_ref] for chunk_ref in chunk_refs if chunk_ref in chunks_by_id]


def _build_dependencies(
    index: int,
    existing_stories: list[UserStory],
    source_dependencies: list[str],
    dependency_refs: list[str],
    relevant_chunks: list[RetrievedChunk],
) -> list[StoryDependency]:
    dependencies: list[StoryDependency] = []
    chunk_refs = [chunk.id for chunk in relevant_chunks]
    for dependency_index, dependency in enumerate(source_dependencies[:3], start=1):
        dependencies.append(
            StoryDependency(
                id=f"DEP-{dependency_index:03d}",
                description=dependency,
                source_refs=[*dependency_refs, *chunk_refs],
            )
        )
    if index > 1 and existing_stories:
        dependencies.append(
            StoryDependency(
                id=f"DEP-{len(dependencies) + 1:03d}",
                description=f"This story depends on completing {existing_stories[-1].id}.",
                depends_on=[existing_stories[-1].id],
                source_refs=[*dependency_refs, *chunk_refs] or source_dependencies[:1],
            )
        )
    return dependencies


def _chunk_refs_for_story(
    payload: GenerateUserStoriesRequest,
    feature_id: str,
    one_line_story_id: str,
    story_chunk_refs: list[str],
) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *story_chunk_refs,
                *_matrix_values_for(payload, feature_id, one_line_story_id, ("chunk_ids", "chunk_refs", "source_chunk_ids")),
            ]
        )
    )


def _requirement_refs_for_story(
    payload: GenerateUserStoriesRequest,
    feature_id: str,
    one_line_story_id: str,
    story_requirement_refs: list[str],
) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *story_requirement_refs,
                *_matrix_values_for(payload, feature_id, one_line_story_id, ("requirement_ids", "requirement_refs")),
            ]
        )
    )


def _matrix_values_for(
    payload: GenerateUserStoriesRequest,
    feature_id: str,
    one_line_story_id: str,
    keys: tuple[str, ...],
) -> list[str]:
    matrix = payload.traceability.get("traceability_matrix", [])
    values: list[str] = []
    for row in matrix:
        if not isinstance(row, dict):
            continue
        row_feature_id = row.get("feature_id") or row.get("feature") or row.get("featureId")
        row_story_id = (
            row.get("one_line_story_id")
            or row.get("story_id")
            or row.get("one_line_story")
            or row.get("storyId")
        )
        if row_feature_id not in {None, feature_id} and row_story_id not in {None, one_line_story_id}:
            continue
        for key in keys:
            raw_value = row.get(key)
            if isinstance(raw_value, list):
                values.extend(str(item) for item in raw_value)
            elif raw_value:
                values.append(str(raw_value))
    return values


def _definition_of_done(acceptance_criteria: list[AcceptanceCriterion]) -> list[str]:
    return [
        f"{criterion.id} is implemented, tested, and traceable to source evidence."
        for criterion in acceptance_criteria
    ]


def _risks_from(dependencies: list[str], non_functional_requirements: list[PlanningArtifact]) -> list[str]:
    risks = [f"Dependency risk: {dependency}" for dependency in dependencies[:2]]
    risks.extend(
        f"Non-functional requirement impact: {requirement.name or requirement.id}"
        for requirement in non_functional_requirements[:2]
    )
    return risks


def _story_confidence_score(
    *,
    chunk_refs: list[str],
    requirement_refs: list[str],
    acceptance_criteria: list[AcceptanceCriterion],
    business_rules: list[str],
    dependencies: list[str],
) -> float:
    score = 0.0
    score += 0.30 if chunk_refs else 0.0
    score += 0.20 if requirement_refs else 0.0
    score += 0.20 if acceptance_criteria else 0.0
    score += 0.15 if business_rules else 0.10
    score += 0.15 if dependencies else 0.10
    return round(min(score, 1.0), 2)


def _as_given_when_then(
    text: str,
    feature_name: str,
    *,
    actor: str = "user",
    goal: str | None = None,
) -> str:
    stripped = text.strip().rstrip(".")
    if all(token in stripped.lower() for token in ["given", "when", "then"]):
        return f"{stripped}."
    concrete_goal = (goal or feature_name).strip().lower()
    return (
        f"Given the documented prerequisites for {concrete_goal} are satisfied, "
        f"When the {actor} attempts to {concrete_goal}, "
        f"Then {stripped[:1].lower() + stripped[1:]}."
    )


def _estimate_points(pack: EvidencePack) -> int:
    """Estimate relative complexity from already-available scoped evidence."""
    complexity = 1
    complexity += min(2, len(pack.acceptance_criteria) // 2)
    complexity += min(2, len(pack.dependencies))
    complexity += 1 if pack.non_functional_requirements else 0
    complexity += 1 if len(pack.requirement_refs) > 2 else 0
    if complexity <= 2:
        return 2
    if complexity <= 4:
        return 3
    if complexity <= 6:
        return 5
    return 8
