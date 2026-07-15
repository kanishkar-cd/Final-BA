from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel

from app.schemas.user_story import (
    AcceptanceCriterion,
    ConfidenceCriterionScore,
    GenerateUserStoriesRequest,
    IssueSeverity,
    MappingReference,
    OneLineStoryInput,
    PlanningArtifact,
    RetrievedChunk,
    StoryDependency,
    TraceabilityMatrixRow,
    UserStory,
    ValidateUserStoriesRequest,
    ValidationIssue,
    ValidationResult,
)


@dataclass(slots=True)
class EvidenceObject:
    """Atomic evidence item shared by generation and validation."""

    id: str
    content: str
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_chunk(cls, chunk: RetrievedChunk) -> "EvidenceObject":
        return cls(id=chunk.id, content=chunk.content, source=chunk.source, metadata=dict(chunk.metadata))


@dataclass(slots=True)
class EvidenceMetadata:
    source: str
    chunk_refs: list[str] = field(default_factory=list)
    requirement_refs: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    rag_context_present: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TraceabilityMetadata:
    workflow_id: str | None
    epic_id: str | None = None
    feature_id: str | None = None
    one_line_story_id: str | None = None
    traceability_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConfidenceMetadata:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    rationale: list[str] = field(default_factory=list)
    input_confidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ValidationMetadata:
    category_scores: dict[str, float] = field(default_factory=dict)
    evidence_match_scores: dict[str, float] = field(default_factory=dict)
    traceability_confidence: dict[str, float] = field(default_factory=dict)
    retry_recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReasoningMetadata:
    explanations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    quality_gate_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QualityGateResult:
    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidencePack:
    """Story-scoped evidence pack used by Agent 3 and understood by Agent 4."""

    workflow_id: str
    story_id: str
    sequence: int
    epic: PlanningArtifact
    feature: PlanningArtifact
    one_line_story: OneLineStoryInput
    retrieved_chunks: list[RetrievedChunk]
    requirements: list[PlanningArtifact]
    non_functional_requirements: list[PlanningArtifact]
    business_rules: list[str]
    acceptance_criteria: list[str]
    dependencies: list[str]
    actors: list[str]
    business_goals: list[str]
    chunk_refs: list[str]
    requirement_refs: list[str]
    traceability_rows: list[dict[str, Any]]
    story_context: dict[str, Any] = field(default_factory=dict)
    planner_metadata: dict[str, Any] = field(default_factory=dict)
    master_context: dict[str, Any] = field(default_factory=dict)
    rag_context: dict[str, Any] = field(default_factory=dict)
    confidence_inputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def actor(self) -> str:
        explicit = (self.one_line_story.actor or "").strip()
        if explicit and explicit.casefold() not in {"user", "actor", "stakeholder"}:
            return explicit
        for actor in self.actors:
            cleaned = actor.strip()
            if cleaned and cleaned.casefold() not in {"user", "actor", "stakeholder"}:
                return cleaned
        return _actor_from_epic(self.epic.name or self.epic.description or "")

    @property
    def business_value(self) -> str:
        if self.one_line_story.business_value:
            return self.one_line_story.business_value
        if self.business_goals:
            return self.business_goals[0].strip().rstrip(".")
        value = self.story_context.get("business_value") or self.master_context.get("business_value")
        if isinstance(value, str) and value.strip():
            return value.strip().rstrip(".")
        if self.feature.name:
            return f"the {self.feature.name} capability delivers its intended business value"
        return "the business process can be completed successfully"

    @property
    def evidence_objects(self) -> list[EvidenceObject]:
        return [EvidenceObject.from_chunk(chunk) for chunk in self.retrieved_chunks]


@dataclass(slots=True)
class EvidenceSource:
    """Normalized validation evidence. It is built only from supplied inputs."""

    chunks: dict[str, str] = field(default_factory=dict)
    requirements: dict[str, str] = field(default_factory=dict)
    business_rules: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    epic_ids: set[str] = field(default_factory=set)
    feature_ids: set[str] = field(default_factory=set)
    one_line_story_ids: set[str] = field(default_factory=set)
    traceability_matrix: list[dict[str, Any]] = field(default_factory=list)
    rag_context: dict[str, Any] = field(default_factory=dict)
    retrieval_metadata: dict[str, Any] = field(default_factory=dict)
    source_name: str = "agent1_output"


@dataclass(slots=True)
class IndependentValidationReport:
    evidence_match_scores: dict[str, float] = field(default_factory=dict)
    traceability_confidence: dict[str, float] = field(default_factory=dict)
    coverage_matrix: list[dict[str, Any]] = field(default_factory=list)
    category_scores: dict[str, float] = field(default_factory=dict)
    explanations: list[str] = field(default_factory=list)
    retry_recommendations: list[str] = field(default_factory=list)
    rag_context_used: bool = False
    retrieval_metadata_present: bool = False

    @property
    def evidence_match_score(self) -> float:
        return average(self.evidence_match_scores.values())

    @property
    def traceability_score(self) -> float:
        return average(self.traceability_confidence.values())


class EvidencePackBuilder:
    """Builds Agent 3 evidence packs without retrieval."""

    def __init__(self, payload: GenerateUserStoriesRequest) -> None:
        self.payload = payload

    def build(self) -> list[EvidencePack]:
        self._validate_payload()
        packs: list[EvidencePack] = []
        epic_lookup = {epic.id: epic for epic in self.payload.epics}
        feature_lookup = {feature.id: feature for feature in self.payload.features}
        story_feature_pairs = [
            (story, feature_id)
            for story in self.payload.one_line_stories
            for feature_id in (story.feature_refs or [story.feature_id])
        ]
        for sequence, (one_line_story, feature_id) in enumerate(story_feature_pairs, start=1):
            feature = feature_lookup.get(feature_id)
            if feature is None:
                raise ValueError(f"One-line story '{one_line_story.id}' references unknown feature '{feature_id}'")
            if not one_line_story.epic_id:
                raise ValueError(f"One-line story '{one_line_story.id}' must reference an Epic for Agent 3")
            epic = epic_lookup.get(one_line_story.epic_id)
            if epic is None:
                raise ValueError(f"One-line story '{one_line_story.id}' references unknown epic '{one_line_story.epic_id}'")
            epic_status = str(epic.metadata.get("status", "")).casefold()
            feature_status = str(feature.metadata.get("status", "")).casefold()
            if epic_status == "rejected" or feature_status == "rejected":
                continue
            chunk_refs = chunk_refs_for_story(self.payload, feature.id, one_line_story.id, one_line_story.chunk_refs)
            requirement_refs = requirement_refs_for_story(
                self.payload,
                feature.id,
                one_line_story.id,
                one_line_story.requirement_refs,
            )
            retrieved_chunks = relevant_chunks_for_refs(self.payload.retrieved_chunks, chunk_refs)
            if self.payload.agent1_output is not None and not retrieved_chunks:
                raise ValueError(
                    f"Epic '{epic.id}', feature '{feature.id}', and one-line story "
                    f"'{one_line_story.id}' have no matching Agent 1 chunk evidence"
                )
            packs.append(
                EvidencePack(
                    workflow_id=self.payload.workflow_id,
                    story_id=f"US-{sequence:03d}",
                    sequence=sequence,
                    epic=epic,
                    feature=feature,
                    one_line_story=one_line_story,
                    retrieved_chunks=retrieved_chunks,
                    requirements=requirements_for_refs(self.payload, requirement_refs),
                    non_functional_requirements=list(self.payload.non_functional_requirements),
                    business_rules=business_rules_for_payload(self.payload),
                    acceptance_criteria=acceptance_criteria_for_payload(self.payload),
                    dependencies=dependencies_for_payload(self.payload, one_line_story, feature),
                    actors=actors_for_payload(self.payload),
                    business_goals=business_goals_for_payload(self.payload),
                    chunk_refs=chunk_refs,
                    requirement_refs=requirement_refs,
                    traceability_rows=traceability_rows_for(self.payload.traceability, feature.id, one_line_story.id),
                    story_context=scoped_context(self.payload.traceability.get("story_context"), feature.id, one_line_story.id),
                    planner_metadata=planner_metadata_for_payload(self.payload),
                    master_context=dict_value(self.payload.traceability.get("master_context")),
                    rag_context=scoped_context(
                        self.payload.traceability.get("rag_context") or self.payload.traceability.get("retrieved_context"),
                        feature.id,
                        one_line_story.id,
                    ),
                    confidence_inputs=dict_value(self.payload.traceability.get("confidence")),
                    metadata=MetadataFactory.pack_source_metadata(self.payload, epic, feature, one_line_story),
                )
            )
        return packs

    def _validate_payload(self) -> None:
        if not self.payload.epics:
            raise ValueError("Agent 3 requires Epics; stories must not be generated from Features alone")
        if not self.payload.features:
            raise ValueError("Agent 3 requires Features linked to Epics")
        if not self.payload.one_line_stories:
            raise ValueError("Agent 3 requires One-Line Stories linked to Features and Epics")
        feature_ids = {feature.id for feature in self.payload.features}
        story_feature_ids = {
            feature_id
            for story in self.payload.one_line_stories
            for feature_id in (story.feature_refs or [story.feature_id])
        }
        missing_story_features = sorted(feature_ids - story_feature_ids)
        if missing_story_features:
            raise ValueError("Every Feature must have a linked One-Line Story for Agent 3: " + ", ".join(missing_story_features))
        epic_ids = {epic.id for epic in self.payload.epics}
        for feature in self.payload.features:
            feature_epic_id = str(feature.metadata.get("epic_id", "")).strip()
            if feature_epic_id and feature_epic_id not in epic_ids:
                raise ValueError(f"Feature '{feature.id}' references unknown epic '{feature_epic_id}'")
        for story in self.payload.one_line_stories:
            unknown_feature_ids = sorted(set(story.feature_refs or [story.feature_id]) - feature_ids)
            if unknown_feature_ids:
                raise ValueError(
                    f"One-line story '{story.id}' references unknown features: "
                    + ", ".join(unknown_feature_ids)
                )
            if not story.epic_id or story.epic_id not in epic_ids:
                raise ValueError(f"One-line story '{story.id}' must reference an existing Epic")


class EvidenceSourceBuilder:
    """Builds Agent 4 evidence sources without retrieval."""

    @classmethod
    def build(cls, payload: ValidateUserStoriesRequest) -> EvidenceSource:
        traceability = payload.traceability
        rag_context = dict_value(traceability.get("rag_context") or traceability.get("retrieved_context"))
        retrieval_metadata = dict_value(
            traceability.get("retrieval_metadata")
            or rag_context.get("retrieval_metadata")
            or dict_value(rag_context.get("retrieved_context")).get("retrieval_metadata")
        )
        evidence = EvidenceSource(
            rag_context=rag_context,
            retrieval_metadata=retrieval_metadata,
            source_name="rag_context" if rag_context else "agent1_output",
        )
        for chunk in payload.retrieved_chunks:
            evidence.chunks[chunk.id] = chunk.content
        cls._consume_agent1_output(evidence, dict_value(traceability.get("agent1_output")))
        cls._consume_rag_context(evidence, rag_context)
        cls._consume_agent3_evidence_packs(evidence, payload)
        for requirement in payload.requirements:
            evidence.requirements[requirement.id] = requirement.name or requirement.description or requirement.id
        evidence.business_rules.extend(payload.business_rules)
        evidence.acceptance_criteria.extend(payload.acceptance_criteria)
        evidence.dependencies.extend(payload.dependencies)
        agent2_output = dict_value(traceability.get("agent2_output"))
        cls._consume_agent2_output(evidence, traceability, agent2_output)
        evidence.traceability_matrix = list_value(
            traceability.get("traceability_matrix") or agent2_output.get("traceability_matrix")
        )
        evidence.business_rules = dedupe_strings(evidence.business_rules)
        evidence.acceptance_criteria = dedupe_strings(evidence.acceptance_criteria)
        evidence.dependencies = dedupe_strings(evidence.dependencies)
        return evidence

    @staticmethod
    def _consume_agent1_output(evidence: EvidenceSource, agent1_output: dict[str, Any]) -> None:
        for chunk in list_value(agent1_output.get("chunks")):
            chunk_id = str(chunk.get("id") or chunk.get("chunk_id") or "")
            content = str(chunk.get("content") or chunk.get("text") or "")
            if chunk_id and content:
                evidence.chunks.setdefault(chunk_id, content)
        for requirement in list_value(agent1_output.get("functional_requirements")):
            req_id = str(requirement.get("id") or requirement.get("requirement_id") or "")
            if req_id:
                evidence.requirements[req_id] = str(requirement.get("name") or requirement.get("description") or req_id)
        evidence.business_rules.extend(string_list(agent1_output.get("business_rules")))
        evidence.acceptance_criteria.extend(string_list(agent1_output.get("acceptance_criteria")))
        evidence.dependencies.extend(string_list(agent1_output.get("dependencies")))

    @staticmethod
    def _consume_rag_context(evidence: EvidenceSource, rag_context: dict[str, Any]) -> None:
        if not rag_context:
            return
        for chunk in extract_rag_chunks(rag_context):
            evidence.chunks[chunk.id] = chunk.content
        evidence.business_rules.extend(string_list(rag_context.get("business_rules")))
        evidence.dependencies.extend(string_list(rag_context.get("dependencies")))
        for requirement in list_value(rag_context.get("supporting_requirements") or rag_context.get("source_requirements")):
            req_id = str(requirement.get("id") or "")
            description = str(requirement.get("description") or requirement.get("name") or "")
            if req_id:
                evidence.requirements[req_id] = description or req_id

    @staticmethod
    def _consume_agent3_evidence_packs(evidence: EvidenceSource, payload: ValidateUserStoriesRequest) -> None:
        for story in payload.generated_user_stories:
            pack = dict_value(story.metadata.get("evidence_pack"))
            if not pack:
                continue
            evidence.business_rules.extend(string_list(pack.get("business_rules")))
            evidence.acceptance_criteria.extend(string_list(pack.get("acceptance_criteria")))
            evidence.dependencies.extend(string_list(pack.get("dependencies")))
            for req_id in string_list(pack.get("requirement_refs")):
                evidence.requirements.setdefault(req_id, req_id)
            for chunk_id in string_list(pack.get("chunk_refs")):
                evidence.chunks.setdefault(chunk_id, "")
            if pack.get("epic_id"):
                evidence.epic_ids.add(str(pack["epic_id"]))
            if pack.get("feature_id"):
                evidence.feature_ids.add(str(pack["feature_id"]))
            if pack.get("one_line_story_id"):
                evidence.one_line_story_ids.add(str(pack["one_line_story_id"]))
            pack_rag_context = dict_value(pack.get("rag_context"))
            if pack_rag_context and not evidence.rag_context:
                evidence.rag_context = pack_rag_context
                evidence.source_name = "rag_context"

    @staticmethod
    def _consume_agent2_output(
        evidence: EvidenceSource,
        traceability: dict[str, Any],
        agent2_output: dict[str, Any],
    ) -> None:
        for epic in [*list_value(traceability.get("epics")), *list_value(agent2_output.get("epics"))]:
            artifact_id = str(epic.get("id") or epic.get("epic_id") or "")
            if artifact_id:
                evidence.epic_ids.add(artifact_id)
        for feature in [*list_value(traceability.get("features")), *list_value(agent2_output.get("features"))]:
            artifact_id = str(feature.get("id") or feature.get("feature_id") or "")
            if artifact_id:
                evidence.feature_ids.add(artifact_id)
        for story in [*list_value(traceability.get("one_line_stories")), *list_value(agent2_output.get("one_line_stories"))]:
            artifact_id = str(story.get("id") or story.get("one_line_story_id") or story.get("story_id") or "")
            if artifact_id:
                evidence.one_line_story_ids.add(artifact_id)


class ConfidenceCalculator:
    """Shared confidence calculator for generation and validation."""

    @staticmethod
    def generation_confidence(
        pack: EvidencePack,
        *,
        acceptance_criteria: list[AcceptanceCriterion],
        dependencies: list[StoryDependency],
    ) -> ConfidenceMetadata:
        components = {
            "hierarchy": 0.20 if pack.epic and pack.feature and pack.one_line_story else 0.0,
            "chunk_evidence": 0.20 if pack.chunk_refs and pack.retrieved_chunks else 0.0,
            "requirement_mapping": 0.15 if pack.requirement_refs or pack.requirements else 0.0,
            "agent1_context": 0.15
            if any([pack.business_rules, pack.acceptance_criteria, pack.dependencies, pack.actors, pack.business_goals])
            else 0.0,
            "agent2_context": 0.15
            if any([pack.planner_metadata, pack.traceability_rows, pack.feature.metadata, pack.epic.metadata])
            else 0.0,
            "field_completeness": 0.10 if acceptance_criteria and dependencies is not None else 0.0,
            "optional_context": 0.05 if any([pack.story_context, pack.master_context, pack.rag_context]) else 0.0,
        }
        return ConfidenceMetadata(
            score=round(min(1.0, sum(components.values())), 2),
            components=components,
            rationale=[
                "Hierarchy validated through Epic, Feature, and One-Line Story.",
                "Chunk and requirement evidence are scored only when supplied references resolve.",
                "Optional RAG context is consumed only when already present in the request.",
            ],
            input_confidence=pack.confidence_inputs,
        )

    @staticmethod
    def text_overlap_score(left: str, right: str) -> float:
        left_tokens = meaningful_tokens(left)
        right_tokens = meaningful_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return round(len(left_tokens & right_tokens) / len(left_tokens), 2)

    @staticmethod
    def category_scores(issues: list[ValidationIssue]) -> dict[str, float]:
        categories = {
            "Field-level validation",
            "Semantic validation",
            "Evidence validation",
            "Contradiction detection",
            "Hallucination detection",
            "Coverage Matrix",
            "Traceability",
            "Relationship Integrity",
        }
        scores: dict[str, float] = {}
        for category in categories:
            related = [issue for issue in issues if category_group(issue.category) == category]
            penalty = sum(severity_penalty(issue.severity) for issue in related)
            scores[category] = round(max(0.0, 1.0 - penalty), 2)
        return scores


class QualityGates:
    """Quality gates shared by Agent 3 output checks and Agent 4 reporting."""

    @staticmethod
    def generation_report(
        pack: EvidencePack,
        acceptance_criteria: list[AcceptanceCriterion],
    ) -> dict[str, Any]:
        valid_chunk_ids = {chunk.id for chunk in pack.retrieved_chunks}
        criteria_with_chunk_refs = [
            criterion.id
            for criterion in acceptance_criteria
            if valid_chunk_ids.intersection(criterion.source_refs)
        ]
        return {
            "hierarchy_present": bool(pack.epic and pack.feature and pack.one_line_story),
            "has_chunk_evidence": bool(pack.chunk_refs),
            "all_chunk_refs_resolved": set(pack.chunk_refs).issubset(valid_chunk_ids) if pack.chunk_refs else True,
            "has_requirement_mapping": bool(pack.requirement_refs or pack.requirements),
            "has_business_rules": bool(pack.business_rules),
            "has_acceptance_criteria": bool(acceptance_criteria),
            "acceptance_criteria_with_chunk_refs": criteria_with_chunk_refs,
            "has_dependencies": bool(pack.dependencies),
            "has_actor": bool(pack.actor),
            "has_business_goals": bool(pack.business_goals),
            "planner_metadata_present": bool(pack.planner_metadata),
            "story_context_present": bool(pack.story_context),
            "master_context_present": bool(pack.master_context),
            "rag_context_present": bool(pack.rag_context),
        }

    @staticmethod
    def apply_validation_report(result: ValidationResult, report: IndependentValidationReport) -> None:
        evidence_score = report.evidence_match_score
        traceability_score = report.traceability_score
        independent_score = average([evidence_score, traceability_score, *report.category_scores.values()])
        if independent_score:
            result.confidence_score = round(min(result.confidence_score, independent_score), 2)
        result.coverage.update(
            {
                "independent_evidence_match": evidence_score >= 0.65,
                "independent_traceability_confidence": traceability_score >= 0.75,
                "rag_context_used": report.rag_context_used,
                "retrieval_metadata_present": report.retrieval_metadata_present,
                "coverage_matrix_complete": all(not row["missing_links"] for row in report.coverage_matrix),
            }
        )
        result.traceability_matrix = merge_traceability_rows(result.traceability_matrix, report.coverage_matrix)
        result.criteria_scores = merge_category_scores(result.criteria_scores, report)
        result.recommendations = dedupe_strings(
            [*result.recommendations, *report.explanations, *report.retry_recommendations]
        )


class SharedValidators:
    """Shared deterministic validators used by Agent 3 and Agent 4."""

    @staticmethod
    def validate_story_against_pack(story: UserStory, pack: EvidencePack) -> None:
        if story.epic_id != pack.epic.id:
            raise ValueError(f"Story '{story.id}' does not reference Evidence Pack epic '{pack.epic.id}'")
        if story.feature_id != pack.feature.id:
            raise ValueError(f"Story '{story.id}' does not reference Evidence Pack feature '{pack.feature.id}'")
        if story.one_line_story_id != pack.one_line_story.id:
            raise ValueError(f"Story '{story.id}' does not reference Evidence Pack one-line story '{pack.one_line_story.id}'")
        if not story.acceptance_criteria:
            raise ValueError(f"Story '{story.id}' must include acceptance criteria")
        if not story.traceability.feature_refs or pack.feature.id not in story.traceability.feature_refs:
            raise ValueError(f"Story '{story.id}' must trace to feature '{pack.feature.id}'")
        if not story.traceability.epic_refs or pack.epic.id not in story.traceability.epic_refs:
            raise ValueError(f"Story '{story.id}' must trace to epic '{pack.epic.id}'")
        if not story.traceability.one_line_story_refs or pack.one_line_story.id not in story.traceability.one_line_story_refs:
            raise ValueError(f"Story '{story.id}' must trace to one-line story '{pack.one_line_story.id}'")
        if pack.requirement_refs:
            story_requirement_refs = {
                *story.traceability.requirement_refs,
                *(mapping.id for mapping in story.requirement_mapping),
            }
            if not set(pack.requirement_refs).issubset(story_requirement_refs):
                raise ValueError(
                    f"Story '{story.id}' does not include all Evidence Pack requirement references"
                )
        if pack.chunk_refs:
            valid_chunk_ids = {chunk.id for chunk in pack.retrieved_chunks}
            story_chunk_ids = set(story.chunk_ids_used) | set(story.traceability.chunk_refs)
            if not set(pack.chunk_refs).issubset(story_chunk_ids):
                raise ValueError(f"Story '{story.id}' does not include all Evidence Pack chunk references")
            if not story_chunk_ids.issubset(valid_chunk_ids):
                raise ValueError(f"Story '{story.id}' references chunks outside the Evidence Pack")

    @classmethod
    def independent_validate(
        cls,
        payload: ValidateUserStoriesRequest,
        evidence: EvidenceSource,
    ) -> tuple[list[ValidationIssue], IndependentValidationReport]:
        issues: list[ValidationIssue] = []
        report = IndependentValidationReport(
            rag_context_used=bool(evidence.rag_context),
            retrieval_metadata_present=bool(evidence.retrieval_metadata),
        )
        story_ids = {story.id for story in payload.generated_user_stories}
        for story in payload.generated_user_stories:
            story_text = story_text_for(story)
            story_issues: list[ValidationIssue] = []
            story_issues.extend(validate_required_fields(story))
            story_issues.extend(validate_semantics(story))
            evidence_issues, evidence_score = validate_evidence(story, story_text, evidence)
            traceability_issues, traceability_score = validate_traceability(story, evidence)
            story_issues.extend(evidence_issues)
            story_issues.extend(traceability_issues)
            story_issues.extend(detect_hallucinations(story, evidence))
            story_issues.extend(detect_contradictions(story, story_text, evidence))
            story_issues.extend(validate_relationships(story, story_ids, evidence))
            issues.extend(story_issues)
            report.evidence_match_scores[story.id] = evidence_score
            report.traceability_confidence[story.id] = traceability_score
            report.coverage_matrix.append(coverage_row(story, evidence, evidence_score, traceability_score))
        issues.extend(validate_coverage(payload.generated_user_stories, evidence))
        report.category_scores = ConfidenceCalculator.category_scores(issues)
        report.explanations = validation_explanations(evidence, report)
        report.retry_recommendations = retry_recommendations(issues, report)
        return issues, report


class MetadataFactory:
    """Shared metadata factory for evidence, traceability, confidence, and reasoning."""

    @staticmethod
    def evidence_pack_id(pack: EvidencePack) -> str:
        return f"EPACK-{pack.epic.id}-{pack.feature.id}-{pack.one_line_story.id}"

    @staticmethod
    def evidence_pack_metadata(pack: EvidencePack) -> dict[str, Any]:
        return {
            "id": MetadataFactory.evidence_pack_id(pack),
            "workflow_id": pack.workflow_id,
            "epic_id": pack.epic.id,
            "feature_id": pack.feature.id,
            "one_line_story_id": pack.one_line_story.id,
            "chunk_refs": pack.chunk_refs,
            "requirement_refs": pack.requirement_refs,
            "business_rules": pack.business_rules,
            "acceptance_criteria": pack.acceptance_criteria,
            "dependencies": pack.dependencies,
            "actors": pack.actors,
            "business_goals": pack.business_goals,
            "planner_metadata": pack.planner_metadata,
            "master_context": pack.master_context,
            "story_context": pack.story_context,
            "rag_context": pack.rag_context,
            "metadata": pack.metadata,
        }

    @staticmethod
    def pack_source_metadata(
        payload: GenerateUserStoriesRequest,
        epic: PlanningArtifact,
        feature: PlanningArtifact,
        one_line_story: OneLineStoryInput,
    ) -> dict[str, Any]:
        return {
            "workflow_id": payload.workflow_id,
            "epic_metadata": dict(epic.metadata),
            "feature_metadata": dict(feature.metadata),
            "one_line_story_priority": one_line_story.priority.value,
            "payload_metadata": dict_value(payload.traceability.get("metadata")),
        }

    @staticmethod
    def assumptions_for_pack(pack: EvidencePack) -> list[str]:
        assumptions = [
            "Generated only from Agent 1 source evidence and Agent 2 planning context.",
            "Generation hierarchy was enforced as Epic -> Feature -> One-Line Story -> Evidence Pack.",
        ]
        if pack.rag_context:
            assumptions.append("Optional RAG context was supplied by the caller and consumed as evidence metadata.")
        if not pack.business_goals:
            assumptions.append("No explicit business goals were supplied in the evidence pack.")
        return assumptions


def validate_required_fields(story: UserStory) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required = {
        "id": story.id,
        "epic_id": story.epic_id,
        "feature_id": story.feature_id,
        "one_line_story_id": story.one_line_story_id,
        "title": story.title,
        "user_story": story.user_story,
        "description": story.description,
        "persona": story.persona,
        "goal": story.goal,
        "business_value": story.business_value,
        "acceptance_criteria": story.acceptance_criteria,
        "traceability": story.traceability,
    }
    for field_name, value in required.items():
        if value is None or value == "" or value == []:
            issues.append(issue("Completeness", field_name, f"Story field '{field_name}' is required for independent validation.", story.id, "Agent 3 Output"))
    return issues


def validate_semantics(story: UserStory) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    lower = story.user_story.lower()
    if not (lower.startswith("as a ") and " i want " in lower and " so that " in lower):
        issues.append(issue("Formatting", "user_story", "User story must follow 'As a <actor>, I want <goal>, so that <benefit>'.", story.id, "Semantic Validation"))
    for criterion in story.acceptance_criteria:
        text = criterion.description.lower()
        if not all(token in text for token in ("given", "when", "then")):
            issues.append(issue("Acceptance Criteria", "acceptance_criteria", f"{criterion.id} must use Given/When/Then format.", story.id, "Semantic Validation"))
    return issues


def validate_evidence(story: UserStory, story_text: str, evidence: EvidenceSource) -> tuple[list[ValidationIssue], float]:
    issues: list[ValidationIssue] = []
    refs = story_chunk_refs(story)
    valid_refs = [chunk_ref for chunk_ref in refs if chunk_ref in evidence.chunks]
    if not refs:
        issues.append(issue("Retrieved Chunk Evidence", "chunk_ids_used", "Story must cite at least one evidence chunk.", story.id, evidence.source_name))
    unknown_refs = sorted(set(refs) - set(evidence.chunks))
    if unknown_refs:
        issues.append(issue("Hallucination Detection", "chunk_ids_used", f"Story cites unknown evidence chunks: {', '.join(unknown_refs)}.", story.id, evidence.source_name))
    evidence_text = " ".join(evidence.chunks[chunk_ref] for chunk_ref in valid_refs)
    if not evidence_text.strip() and evidence.chunks:
        evidence_text = " ".join(evidence.chunks.values())
    score = ConfidenceCalculator.text_overlap_score(story_text, evidence_text)
    if evidence.chunks and score < 0.18:
        issues.append(issue("Retrieved Chunk Evidence", "description", "Story text has low semantic overlap with available evidence.", story.id, evidence.source_name))
    return issues, score


def validate_traceability(story: UserStory, evidence: EvidenceSource) -> tuple[list[ValidationIssue], float]:
    issues: list[ValidationIssue] = []
    checks = {
        "chunk_refs": bool(story_chunk_refs(story)),
        "requirement_refs": bool(story.traceability.requirement_refs or story.requirement_mapping),
        "epic_refs": bool(story.traceability.epic_refs or story.epic_id),
        "feature_refs": bool(story.traceability.feature_refs or story.feature_id),
        "one_line_story_refs": bool(story.traceability.one_line_story_refs or story.one_line_story_id),
    }
    for field_name, passed in checks.items():
        if not passed:
            issues.append(issue("Traceability", field_name, f"Traceability field '{field_name}' is missing.", story.id, "Traceability Matrix"))
    if evidence.traceability_matrix and not matrix_rows_for_story(story, evidence.traceability_matrix):
        issues.append(issue("Traceability", "traceability_matrix", "Story is not represented in the supplied traceability matrix.", story.id, "Traceability Matrix"))
    return issues, sum(1 for passed in checks.values() if passed) / len(checks)


def detect_hallucinations(story: UserStory, evidence: EvidenceSource) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    allowed_rules = {normalize(rule) for rule in evidence.business_rules}
    if allowed_rules:
        for rule in story.business_rules:
            if normalize(rule) not in allowed_rules:
                issues.append(issue("Hallucination Detection", "business_rules", f"Business rule is not supported by evidence: {rule}", story.id, evidence.source_name))
    allowed_dependencies = {normalize(dep) for dep in evidence.dependencies}
    if allowed_dependencies:
        for dependency in story.dependencies:
            if dependency.depends_on:
                continue
            if normalize(dependency.description) not in allowed_dependencies:
                issues.append(issue("Hallucination Detection", "dependencies", f"Dependency is not supported by evidence: {dependency.description}", story.id, evidence.source_name))
    if evidence.epic_ids and story.epic_id not in evidence.epic_ids:
        issues.append(unknown_artifact_issue(story.id, "epic_id", story.epic_id, "Agent 2 Output"))
    if evidence.feature_ids and story.feature_id not in evidence.feature_ids:
        issues.append(unknown_artifact_issue(story.id, "feature_id", story.feature_id, "Agent 2 Output"))
    if evidence.one_line_story_ids and story.one_line_story_id not in evidence.one_line_story_ids:
        issues.append(unknown_artifact_issue(story.id, "one_line_story_id", story.one_line_story_id, "Agent 2 Output"))
    return issues


def detect_contradictions(story: UserStory, story_text: str, evidence: EvidenceSource) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    evidence_text = " ".join(evidence.chunks.values())
    if not evidence_text:
        return issues
    story_lower = story_text.lower()
    evidence_lower = evidence_text.lower()
    for required_term, conflicting_term in [
        ("must", "optional"),
        ("required", "optional"),
        ("shall", "may"),
        ("cannot", "can "),
        ("not allowed", "allowed"),
        ("prohibited", "permitted"),
    ]:
        if required_term in evidence_lower and conflicting_term in story_lower:
            issues.append(
                issue(
                    "Consistency",
                    "description",
                    f"Potential contradiction: evidence contains '{required_term}' while story uses '{conflicting_term}'.",
                    story.id,
                    evidence.source_name,
                    severity=IssueSeverity.WARNING,
                )
            )
    return issues


def validate_relationships(story: UserStory, story_ids: set[str], evidence: EvidenceSource) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for dependency in story.dependencies:
        missing = [dep_id for dep_id in dependency.depends_on if dep_id not in story_ids]
        if missing:
            issues.append(issue("Relationship Integrity", "dependencies", f"Dependency references unknown generated stories: {', '.join(missing)}.", story.id, "Agent 3 Output"))
    for row in matrix_rows_for_story(story, evidence.traceability_matrix):
        row_feature = row.get("feature_id") or row.get("feature") or row.get("featureId")
        row_story = row.get("one_line_story_id") or row.get("story_id") or row.get("storyId")
        if row_feature and row_feature != story.feature_id:
            issues.append(issue("Relationship Integrity", "feature_id", "Story feature does not match traceability matrix feature.", story.id, "Traceability Matrix"))
        if row_story and row_story not in {story.one_line_story_id, story.id}:
            issues.append(issue("Relationship Integrity", "one_line_story_id", "Story one-line-story mapping does not match traceability matrix.", story.id, "Traceability Matrix"))
    return issues


def validate_coverage(stories: list[UserStory], evidence: EvidenceSource) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    requirement_refs = {
        ref
        for story in stories
        for ref in [*story.traceability.requirement_refs, *[mapping.id for mapping in story.requirement_mapping]]
    }
    missing_requirements = sorted(set(evidence.requirements) - requirement_refs)
    if missing_requirements:
        issues.append(issue("Coverage", "requirement_mapping", f"Requirements not covered by generated stories: {', '.join(missing_requirements)}.", None, "Coverage Matrix"))
    cited_chunks = {chunk_ref for story in stories for chunk_ref in story_chunk_refs(story)}
    missing_chunks = sorted(set(evidence.chunks) - cited_chunks)
    if evidence.chunks and missing_chunks:
        issues.append(issue("Retrieved Chunk Evidence", "retrieved_chunks", f"Evidence chunks not cited by any generated story: {', '.join(missing_chunks[:10])}.", None, "Coverage Matrix", severity=IssueSeverity.WARNING))
    return issues


def coverage_row(story: UserStory, evidence: EvidenceSource, evidence_score: float, traceability_score: float) -> dict[str, Any]:
    requirement_refs = list(dict.fromkeys([*story.traceability.requirement_refs, *[mapping.id for mapping in story.requirement_mapping]]))
    chunk_refs = story_chunk_refs(story)
    missing_links: list[str] = []
    if not requirement_refs:
        missing_links.append("requirements")
    if not chunk_refs:
        missing_links.append("chunks")
    if not story.epic_id:
        missing_links.append("epic")
    if not story.feature_id:
        missing_links.append("feature")
    if not story.one_line_story_id:
        missing_links.append("one_line_story")
    return {
        "story_id": story.id,
        "requirement_refs": requirement_refs,
        "chunk_refs": chunk_refs,
        "epic_refs": [story.epic_id] if story.epic_id else [],
        "feature_refs": [story.feature_id] if story.feature_id else [],
        "one_line_story_refs": [story.one_line_story_id] if story.one_line_story_id else [],
        "dependency_refs": list(story.traceability.dependency_refs),
        "missing_links": missing_links,
        "evidence_match_score": evidence_score,
        "traceability_confidence": traceability_score,
        "validated_against": evidence.source_name,
    }


def merge_traceability_rows(existing_rows: list[TraceabilityMatrixRow], coverage_rows: list[dict[str, Any]]) -> list[TraceabilityMatrixRow]:
    rows_by_story = {row.story_id: row for row in existing_rows}
    for row in coverage_rows:
        story_id = str(row["story_id"])
        if story_id in rows_by_story:
            current = rows_by_story[story_id]
            current.missing_links = dedupe_strings([*current.missing_links, *row["missing_links"]])
            continue
        rows_by_story[story_id] = TraceabilityMatrixRow(
            story_id=story_id,
            requirement_refs=list(row["requirement_refs"]),
            chunk_refs=list(row["chunk_refs"]),
            epic_refs=list(row["epic_refs"]),
            feature_refs=list(row["feature_refs"]),
            one_line_story_refs=list(row["one_line_story_refs"]),
            dependency_refs=list(row["dependency_refs"]),
            missing_links=list(row["missing_links"]),
        )
    return list(rows_by_story.values())


def merge_category_scores(
    existing_scores: list[ConfidenceCriterionScore],
    report: IndependentValidationReport,
) -> list[ConfidenceCriterionScore]:
    scores = list(existing_scores)
    scores.append(
        ConfidenceCriterionScore(
            category="Independent Evidence Match",
            score=round(report.evidence_match_score * 10, 2),
            max_score=10.0,
            passed=report.evidence_match_score >= 0.65,
            issue_count=0,
            details=[f"Average evidence match score: {report.evidence_match_score:.2f}"],
        )
    )
    scores.append(
        ConfidenceCriterionScore(
            category="Traceability Confidence",
            score=round(report.traceability_score * 10, 2),
            max_score=10.0,
            passed=report.traceability_score >= 0.75,
            issue_count=0,
            details=[f"Average traceability confidence: {report.traceability_score:.2f}"],
        )
    )
    for category, score in report.category_scores.items():
        scores.append(
            ConfidenceCriterionScore(
                category=f"Independent {category}",
                score=round(score * 10, 2),
                max_score=10.0,
                passed=score >= 0.75,
                issue_count=0,
                details=[f"Independent category score: {score:.2f}"],
            )
        )
    return scores


def validation_explanations(evidence: EvidenceSource, report: IndependentValidationReport) -> list[str]:
    source = "optional RAG context" if report.rag_context_used else "Agent 1 evidence"
    return [
        f"Independent validation used {source}; no document retrieval was performed.",
        f"Evidence Match Score: {report.evidence_match_score:.2f}.",
        f"Traceability Confidence: {report.traceability_score:.2f}.",
        f"Validated evidence set: {len(evidence.chunks)} chunks, {len(evidence.requirements)} requirements, "
        f"{len(evidence.business_rules)} business rules, {len(evidence.dependencies)} dependencies.",
    ]


def retry_recommendations(issues: list[ValidationIssue], report: IndependentValidationReport) -> list[str]:
    recommendations: list[str] = []
    categories = {validation_issue.category for validation_issue in issues}
    if "Hallucination Detection" in categories:
        recommendations.append("Retry Agent 3 with stricter evidence-pack grounding; generated content is unsupported.")
    if "Retrieved Chunk Evidence" in categories or report.evidence_match_score < 0.65:
        recommendations.append("Retry Agent 3 using the mapped chunks and require every generated field to cite evidence.")
    if "Traceability" in categories or report.traceability_score < 0.75:
        recommendations.append("Retry from planning context if traceability matrix links are missing or inconsistent.")
    if "Consistency" in categories:
        recommendations.append("Send to human review if contradiction warnings remain after regeneration.")
    return recommendations


def requirements_for_refs(payload: GenerateUserStoriesRequest, requirement_refs: list[str]) -> list[PlanningArtifact]:
    requirements = payload.requirements or payload.functional_requirements
    if not requirement_refs:
        return list(requirements)
    selected = [requirement for requirement in requirements if requirement.id in requirement_refs]
    return selected or list(requirements)


def business_rules_for_payload(payload: GenerateUserStoriesRequest) -> list[str]:
    rules = [*payload.business_rules, *string_list(payload.traceability.get("business_rules"))]
    if payload.agent1_output is not None:
        rules.extend(payload.agent1_output.business_rules)
    return dedupe_strings(rules)


def acceptance_criteria_for_payload(payload: GenerateUserStoriesRequest) -> list[str]:
    criteria = [*payload.acceptance_criteria, *string_list(payload.traceability.get("acceptance_criteria"))]
    if payload.agent1_output is not None:
        criteria.extend(payload.agent1_output.acceptance_criteria)
    return dedupe_strings(criteria)


def dependencies_for_payload(
    payload: GenerateUserStoriesRequest,
    one_line_story: OneLineStoryInput,
    feature: PlanningArtifact,
) -> list[str]:
    """Return dependencies explicitly scoped to the selected feature/story."""
    dependencies = [
        *one_line_story.dependency_refs,
        *string_list(feature.metadata.get("dependencies")),
    ]
    for row in traceability_rows_for(
        payload.traceability,
        feature.id,
        one_line_story.id,
    ):
        dependencies.extend(string_list(row.get("dependencies")))
        dependencies.extend(string_list(row.get("dependency_refs")))
    return dedupe_strings(dependencies)


def actors_for_payload(payload: GenerateUserStoriesRequest) -> list[str]:
    actors = [*payload.actors, *string_list(payload.traceability.get("actors"))]
    if payload.agent1_output is not None:
        actors.extend(payload.agent1_output.actors)
    return dedupe_strings(actors)


def _actor_from_epic(epic_text: str) -> str:
    """Infer a stable business actor only when Agent 1 supplied none."""
    text = epic_text.casefold()
    actor_keywords = (
        (("content", "cms", "publish"), "Content Administrator"),
        (("marketing", "campaign", "seo", "brand"), "Marketing Team"),
        (("sales", "lead", "customer relationship"), "Sales Team"),
        (("develop", "api", "integration", "technical platform"), "Developer"),
        (("design", "user interface", "branding"), "Designer"),
        (("enterprise", "account", "client portal"), "Enterprise Customer"),
    )
    for keywords, actor in actor_keywords:
        if any(keyword in text for keyword in keywords):
            return actor
    return "Website Visitor"


def business_goals_for_payload(payload: GenerateUserStoriesRequest) -> list[str]:
    goals = [*payload.business_goals, *string_list(payload.traceability.get("business_goals"))]
    if payload.agent1_output is not None:
        goals.extend(string_list(payload.agent1_output.traceability_metadata.get("business_goals")))
    return dedupe_strings(goals)


def planner_metadata_for_payload(payload: GenerateUserStoriesRequest) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if payload.agent2_output is not None:
        metadata.update(payload.agent2_output.planning_metadata)
    trace_metadata = payload.traceability.get("planning_metadata")
    if isinstance(trace_metadata, dict):
        metadata.update(trace_metadata)
    planner_metadata = payload.traceability.get("planner_metadata")
    if isinstance(planner_metadata, dict):
        metadata.update(planner_metadata)
    return metadata


def chunk_refs_for_story(
    payload: GenerateUserStoriesRequest,
    feature_id: str,
    one_line_story_id: str,
    story_chunk_refs: list[str],
) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *story_chunk_refs,
                *matrix_values_for(payload.traceability, feature_id, one_line_story_id, ("chunk_ids", "chunk_refs", "source_chunk_ids")),
            ]
        )
    )


def requirement_refs_for_story(
    payload: GenerateUserStoriesRequest,
    feature_id: str,
    one_line_story_id: str,
    story_requirement_refs: list[str],
) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *story_requirement_refs,
                *matrix_values_for(payload.traceability, feature_id, one_line_story_id, ("requirement_ids", "requirement_refs")),
            ]
        )
    )


def matrix_values_for(
    traceability: dict[str, Any],
    feature_id: str,
    one_line_story_id: str,
    keys: tuple[str, ...],
) -> list[str]:
    values: list[str] = []
    for row in list_value(traceability.get("traceability_matrix")):
        row_feature_id = row.get("feature_id") or row.get("feature") or row.get("featureId")
        row_story_id = row.get("one_line_story_id") or row.get("story_id") or row.get("one_line_story") or row.get("storyId")
        if row_feature_id is not None and row_feature_id != feature_id:
            continue
        if row_story_id is not None and row_story_id != one_line_story_id:
            continue
        for key in keys:
            raw_value = row.get(key)
            if isinstance(raw_value, list):
                values.extend(str(item) for item in raw_value)
            elif raw_value:
                values.append(str(raw_value))
    return values


def traceability_rows_for(traceability: dict[str, Any], feature_id: str, one_line_story_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in list_value(traceability.get("traceability_matrix")):
        row_feature_id = row.get("feature_id") or row.get("feature") or row.get("featureId")
        row_story_id = row.get("one_line_story_id") or row.get("story_id") or row.get("one_line_story") or row.get("storyId")
        if row_feature_id is not None and row_feature_id != feature_id:
            continue
        if row_story_id is not None and row_story_id != one_line_story_id:
            continue
        rows.append(dict(row))
    return rows


def relevant_chunks_for_refs(chunks: list[RetrievedChunk], chunk_refs: list[str]) -> list[RetrievedChunk]:
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    return [chunks_by_id[chunk_ref] for chunk_ref in chunk_refs if chunk_ref in chunks_by_id]


def source_chunk_references(relevant_chunks: list[RetrievedChunk]) -> list[MappingReference]:
    return [
        MappingReference(id=chunk.id, name=chunk.source, source=chunk.content[:240])
        for chunk in relevant_chunks
    ]


def extract_rag_chunks(rag_context: dict[str, Any]) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    raw_chunks = (
        rag_context.get("source_chunks")
        or rag_context.get("chunks")
        or dict_value(rag_context.get("retrieved_context")).get("source_chunks")
        or []
    )
    for raw_chunk in list_value(raw_chunks):
        chunk_id = str(raw_chunk.get("id") or raw_chunk.get("chunk_id") or "")
        content = str(raw_chunk.get("content") or raw_chunk.get("text") or "")
        if chunk_id and content:
            chunks.append(
                RetrievedChunk(
                    id=chunk_id,
                    content=content,
                    source=raw_chunk.get("source"),
                    metadata=dict_value(raw_chunk.get("metadata")),
                )
            )
    return chunks


def story_text_for(story: UserStory) -> str:
    parts = [
        story.title,
        story.user_story,
        story.description,
        story.persona or "",
        story.goal or "",
        story.business_value or "",
        " ".join(criterion.description for criterion in story.acceptance_criteria),
        " ".join(story.business_rules),
        " ".join(dependency.description for dependency in story.dependencies),
    ]
    return " ".join(part for part in parts if part)


def story_chunk_refs(story: UserStory) -> list[str]:
    refs = [*story.chunk_ids_used, *story.traceability.chunk_refs, *[ref.id for ref in story.source_chunk_references]]
    raw_links = story.traceability_links
    if isinstance(raw_links, dict):
        refs.extend(string_list(raw_links.get("chunk_ids") or raw_links.get("chunk_refs")))
    return list(dict.fromkeys(str(ref) for ref in refs if ref))


def matrix_rows_for_story(story: UserStory, matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in matrix:
        if not isinstance(row, dict):
            continue
        row_feature = row.get("feature_id") or row.get("feature") or row.get("featureId")
        row_story = row.get("one_line_story_id") or row.get("story_id") or row.get("storyId")
        row_feature_refs = set(string_list(row.get("feature_refs")))
        row_one_line_refs = set(string_list(row.get("one_line_story_refs")))
        feature_matches = row_feature in {None, story.feature_id} or story.feature_id in row_feature_refs
        story_matches = (
            row_story in {None, story.one_line_story_id, story.id}
            or story.one_line_story_id in row_one_line_refs
        )
        if feature_matches and story_matches:
            rows.append(row)
    return rows


def scoped_context(raw_context: Any, feature_id: str, one_line_story_id: str) -> dict[str, Any]:
    if not isinstance(raw_context, dict):
        return {}
    for key in (one_line_story_id, feature_id):
        scoped = raw_context.get(key)
        if isinstance(scoped, dict):
            return dict(scoped)
    items = raw_context.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and (item.get("one_line_story_id") == one_line_story_id or item.get("feature_id") == feature_id):
                return dict(item)
    return dict(raw_context)


def context_summary(context: dict[str, Any]) -> str:
    if not context:
        return ""
    summary = context.get("summary") or context.get("description") or context.get("business_value")
    if isinstance(summary, str):
        return summary[:240]
    return ", ".join(str(key) for key in list(context)[:5])


def meaningful_tokens(text: str) -> set[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "that",
        "with",
        "from",
        "this",
        "when",
        "then",
        "given",
        "user",
        "story",
        "system",
        "can",
        "want",
        "will",
        "shall",
        "must",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in stop_words
    }


def unknown_artifact_issue(story_id: str, field: str, value: str | None, source: str) -> ValidationIssue:
    return issue(
        "Hallucination Detection",
        field,
        f"Story references an artifact not supplied by upstream evidence: {value}",
        story_id,
        source,
    )


def issue(
    category: str,
    field: str,
    message: str,
    story_id: str | None,
    source_reference: str,
    *,
    severity: IssueSeverity = IssueSeverity.ERROR,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        category=category,
        story_id=story_id,
        field=field,
        message=message,
        source_reference=source_reference,
        suggested_action="Retry generation with evidence grounding or send to human review.",
    )


def dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value) if isinstance(value, dict) else {}


def list_value(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, BaseModel):
            result.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            result.append(item)
    return result


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item]
    return []


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", str(value).strip())
        key = normalized.lower()
        if normalized and key not in seen:
            deduped.append(normalized)
            seen.add(key)
    return deduped


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def average(values: Any) -> float:
    values_list = [float(value) for value in values if value is not None]
    if not values_list:
        return 0.0
    return round(sum(values_list) / len(values_list), 2)


def severity_penalty(severity: IssueSeverity) -> float:
    return {
        IssueSeverity.INFO: 0.02,
        IssueSeverity.WARNING: 0.05,
        IssueSeverity.ERROR: 0.15,
        IssueSeverity.CRITICAL: 0.25,
    }[severity]


def category_group(category: str) -> str:
    if category in {"Completeness", "Formatting", "Acceptance Criteria"}:
        return "Field-level validation" if category == "Completeness" else "Semantic validation"
    if category == "Retrieved Chunk Evidence":
        return "Evidence validation"
    if category == "Consistency":
        return "Contradiction detection"
    if category == "Hallucination Detection":
        return "Hallucination detection"
    if category == "Coverage":
        return "Coverage Matrix"
    if category == "Traceability":
        return "Traceability"
    if category == "Relationship Integrity":
        return "Relationship Integrity"
    return category
