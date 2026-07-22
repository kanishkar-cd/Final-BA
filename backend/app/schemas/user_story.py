from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class PipelineStatus(StrEnum):
    PENDING = "PENDING"
    GENERATED = "GENERATED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RegenerationTarget(StrEnum):
    NONE = "NONE"
    AGENT_1_REQUIREMENT_ANALYSIS = "AGENT_1_REQUIREMENT_ANALYSIS"
    AGENT_2_PLANNING = "AGENT_2_PLANNING"
    AGENT_3_USER_STORY = "AGENT_3_USER_STORY"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class Priority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IssueSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditAction(StrEnum):
    GENERATION_STARTED = "GENERATION_STARTED"
    STORIES_GENERATED = "STORIES_GENERATED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    RETRY_REQUESTED = "RETRY_REQUESTED"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    STORY_MODIFIED = "STORY_MODIFIED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AcceptanceCriterion(BaseModel):
    id: str
    description: str
    source_refs: list[str] = Field(default_factory=list)


class StoryDependency(BaseModel):
    id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class InvestCompliance(BaseModel):
    independent: bool = True
    negotiable: bool = True
    valuable: bool = True
    estimable: bool = True
    small: bool = True
    testable: bool = True
    notes: list[str] = Field(default_factory=list)


class MappingReference(BaseModel):
    id: str
    name: str | None = None
    source: str | None = None


class TraceabilityLink(BaseModel):
    workflow_id: str
    requirement_refs: list[str] = Field(default_factory=list)
    chunk_refs: list[str] = Field(default_factory=list)
    epic_refs: list[str] = Field(default_factory=list)
    feature_refs: list[str] = Field(default_factory=list)
    one_line_story_refs: list[str] = Field(default_factory=list)
    dependency_refs: list[str] = Field(default_factory=list)
    generated_by: str | None = None
    validated_by: str | None = None
    approved_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserStory(BaseModel):
    id: str
    feature_id: str
    epic_id: str | None = None
    one_line_story_id: str | None = None
    chunk_ids_used: list[str] = Field(default_factory=list)
    title: str
    user_story: str
    description: str
    persona: str | None = None
    goal: str | None = None
    business_value: str | None = None
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    dependencies: list[StoryDependency] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    requirement_mapping: list[MappingReference] = Field(default_factory=list)
    epic_mapping: list[MappingReference] = Field(default_factory=list)
    feature_mapping: list[MappingReference] = Field(default_factory=list)
    source_chunk_references: list[MappingReference] = Field(default_factory=list)
    priority: Priority = Priority.MEDIUM
    story_points: int = Field(default=3, ge=1)
    confidence_score: float = Field(default=1.0, ge=0, le=1)
    retry_attempts: int = Field(default=0, ge=0)
    invest_compliance: InvestCompliance = Field(default_factory=InvestCompliance)
    traceability: TraceabilityLink
    traceability_links: dict[str, Any] = Field(default_factory=dict)
    generation_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("story_points")
    @classmethod
    def story_points_should_use_fibonacci(cls, value: int) -> int:
        if value not in {1, 2, 3, 5, 8, 13}:
            raise ValueError("story_points must be one of 1, 2, 3, 5, 8, 13")
        return value


class PlanningArtifact(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_artifact_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for alias in ("requirement_id", "epic_id", "feature_id", "artifact_id"):
            if alias in normalized and "id" not in normalized:
                normalized["id"] = normalized[alias]
        if "title" in normalized and "name" not in normalized:
            normalized["name"] = normalized["title"]
        return normalized


class OneLineStoryInput(BaseModel):
    id: str
    feature_id: str
    feature_refs: list[str] = Field(default_factory=list)
    epic_id: str | None = None
    summary: str
    actor: str | None = None
    business_value: str | None = None
    priority: Priority = Priority.MEDIUM
    requirement_refs: list[str] = Field(default_factory=list)
    chunk_refs: list[str] = Field(default_factory=list)
    dependency_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_story_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for alias in ("story_id", "one_line_story_id"):
            if alias in normalized and "id" not in normalized:
                normalized["id"] = normalized[alias]
        for alias in ("one_line_story", "one_line_text", "title"):
            if alias in normalized and "summary" not in normalized:
                normalized["summary"] = normalized[alias]
        if "chunk_ids" in normalized and "chunk_refs" not in normalized:
            normalized["chunk_refs"] = normalized["chunk_ids"]
        if "requirement_ids" in normalized and "requirement_refs" not in normalized:
            normalized["requirement_refs"] = normalized["requirement_ids"]
        if "dependency_ids" in normalized and "dependency_refs" not in normalized:
            normalized["dependency_refs"] = normalized["dependency_ids"]
        if "feature_ids" in normalized and "feature_refs" not in normalized:
            normalized["feature_refs"] = normalized["feature_ids"]
        return normalized


class RetrievedChunk(BaseModel):
    id: str
    content: str
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_chunk_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for alias in ("chunk_id", "chunkId"):
            if alias in normalized and "id" not in normalized:
                normalized["id"] = normalized[alias]
        for alias in ("text", "chunk_text", "page_content"):
            if alias in normalized and "content" not in normalized:
                normalized["content"] = normalized[alias]
        return normalized


class Agent1Output(BaseModel):
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    functional_requirements: list[PlanningArtifact] = Field(default_factory=list)
    non_functional_requirements: list[PlanningArtifact] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    traceability_metadata: dict[str, Any] = Field(default_factory=dict)


class Agent2Output(BaseModel):
    epics: list[PlanningArtifact] = Field(default_factory=list)
    features: list[PlanningArtifact] = Field(default_factory=list)
    one_line_stories: list[OneLineStoryInput] = Field(default_factory=list)
    traceability_matrix: list[dict[str, Any]] = Field(default_factory=list)
    planning_metadata: dict[str, Any] = Field(default_factory=dict)


class PlanningPipelineOutput(BaseModel):
    requirements: list[PlanningArtifact] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    functional_requirements: list[PlanningArtifact] = Field(default_factory=list)
    non_functional_requirements: list[PlanningArtifact] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    business_goals: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    epics: list[PlanningArtifact] = Field(default_factory=list)
    features: list[PlanningArtifact] = Field(default_factory=list)
    one_line_stories: list[OneLineStoryInput] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    traceability: dict[str, Any] = Field(default_factory=dict)
    agent1_output: Agent1Output | None = None
    agent2_output: Agent2Output | None = None


class GenerateUserStoriesRequest(PlanningPipelineOutput):
    workflow_id: str = Field(default_factory=lambda: f"WF-{uuid4().hex[:8].upper()}")
    confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    max_retry_attempts: int = Field(default=3, ge=0, le=5)

    @model_validator(mode="after")
    def normalize_agent_outputs(self) -> "GenerateUserStoriesRequest":
        if self.agent1_output is not None:
            self.retrieved_chunks = self.retrieved_chunks or self.agent1_output.chunks
            self.actors = self.actors or self.agent1_output.actors
            self.functional_requirements = (
                self.functional_requirements or self.agent1_output.functional_requirements
            )
            self.non_functional_requirements = (
                self.non_functional_requirements or self.agent1_output.non_functional_requirements
            )
            self.business_rules = self.business_rules or self.agent1_output.business_rules
            self.dependencies = self.dependencies or self.agent1_output.dependencies
            self.acceptance_criteria = self.acceptance_criteria or self.agent1_output.acceptance_criteria
            self.traceability = {
                **self.agent1_output.traceability_metadata,
                **self.traceability,
            }

        if self.agent2_output is not None:
            self.epics = self.epics or self.agent2_output.epics
            self.features = self.features or self.agent2_output.features
            self.one_line_stories = self.one_line_stories or self.agent2_output.one_line_stories
            self.traceability = {
                **self.traceability,
                # Empty placeholders must not discard Agent 2's planning handoff.
                "traceability_matrix": (
                    self.traceability.get("traceability_matrix")
                    or self.agent2_output.traceability_matrix
                ),
                "planning_metadata": (
                    self.traceability.get("planning_metadata")
                    or self.agent2_output.planning_metadata
                ),
            }

        self.requirements = self.requirements or self.functional_requirements
        return self

    @model_validator(mode="after")
    def retrieved_chunks_are_required_for_story_generation(self) -> "GenerateUserStoriesRequest":
        if self.agent1_output is not None and not self.retrieved_chunks:
            raise ValueError("retrieved_chunks are mandatory for Agent 3 user story generation")

        available_chunk_ids = {chunk.id for chunk in self.retrieved_chunks}
        for one_line_story in self.one_line_stories:
            mapped_chunk_refs = _matrix_values_for(
                self.traceability.get("traceability_matrix", []),
                feature_id=one_line_story.feature_id,
                one_line_story_id=one_line_story.id,
                keys=("chunk_ids", "chunk_refs", "source_chunk_ids"),
            )
            chunk_refs = list(dict.fromkeys([*one_line_story.chunk_refs, *mapped_chunk_refs]))
            if self.agent1_output is not None and not chunk_refs:
                raise ValueError(
                    f"one_line_story '{one_line_story.id}' must reference at least one Agent 1 chunk"
                )
            if not self.retrieved_chunks:
                continue
            missing_chunk_refs = [
                chunk_ref
                for chunk_ref in chunk_refs
                if chunk_ref not in available_chunk_ids
            ]
            if missing_chunk_refs:
                raise ValueError(
                    f"one_line_story '{one_line_story.id}' references unknown chunks: "
                    f"{', '.join(missing_chunk_refs)}"
                )
        return self


class ValidationIssue(BaseModel):
    issue_id: str = Field(default_factory=lambda: f"ISSUE-{uuid4().hex[:8].upper()}")
    severity: IssueSeverity = IssueSeverity.ERROR
    category: str = Field(default="GENERAL")
    story_id: str | None = None
    field: str = Field(default="general")
    message: str = Field(default="")
    source_reference: str | None = None
    suggested_action: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_issue_data(cls, data: Any) -> Any:
        if isinstance(data, dict):
            normalized = dict(data)
            if not normalized.get("category"):
                normalized["category"] = "GENERAL"
            if not normalized.get("field"):
                normalized["field"] = "general"
            if not normalized.get("message"):
                normalized["message"] = str(normalized.get("description") or normalized.get("issue") or "Validation issue detected")
            return normalized
        return data


class TraceabilityMatrixRow(BaseModel):
    story_id: str
    requirement_refs: list[str] = Field(default_factory=list)
    chunk_refs: list[str] = Field(default_factory=list)
    epic_refs: list[str] = Field(default_factory=list)
    feature_refs: list[str] = Field(default_factory=list)
    one_line_story_refs: list[str] = Field(default_factory=list)
    dependency_refs: list[str] = Field(default_factory=list)
    missing_links: list[str] = Field(default_factory=list)


class ConfidenceCriterionScore(BaseModel):
    category: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    passed: bool
    issue_count: int = 0
    details: list[str] = Field(default_factory=list)


class StoryValidationSummary(BaseModel):
    story_id: str
    confidence_score: float = Field(ge=0, le=1)
    passed: bool
    retry_required: bool = False
    review_required: bool = False
    retry_attempts: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    criteria_scores: list[ConfidenceCriterionScore] = Field(default_factory=list)


class ValidationResult(BaseModel):
    validation_status: PipelineStatus
    passed: bool
    confidence_score: float
    threshold: float
    issues: list[ValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    retry_required: bool = False
    review_required: bool = False
    regeneration_target: RegenerationTarget = RegenerationTarget.NONE
    failed_story_ids: list[str] = Field(default_factory=list)
    upstream_issue_categories: list[str] = Field(default_factory=list)
    story_results: list[StoryValidationSummary] = Field(default_factory=list)
    traceability_matrix: list[TraceabilityMatrixRow] = Field(default_factory=list)
    criteria_scores: list[ConfidenceCriterionScore] = Field(default_factory=list)
    coverage: dict[str, bool] = Field(default_factory=dict)


class UserStoryGenerationResponse(BaseModel):
    workflow_id: str
    status: PipelineStatus
    stories: list[UserStory]
    user_stories: list[UserStory] = Field(default_factory=list)
    traceability_links: list[TraceabilityLink] = Field(default_factory=list)
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = Field(default=0.0, ge=0, le=1)
    validation: ValidationResult
    retry_attempts: int = 0
    review_required: bool = False
    audit_trail: list["AuditEvent"] = Field(default_factory=list)
    workflow_history: list["WorkflowHistoryEvent"] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ValidateUserStoriesRequest(PlanningPipelineOutput):
    workflow_id: str | None = None
    generated_user_stories: list[UserStory]
    confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    max_retry_attempts: int = Field(default=3, ge=0, le=5)


class RetryUserStoriesRequest(GenerateUserStoriesRequest):
    previous_stories: list[UserStory] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    retry_attempt: int = Field(default=1, ge=1)


class ReviewDecisionRequest(BaseModel):
    workflow_id: str
    reviewed_by: str
    approved: bool = True
    comments: str | None = None


class ModifyStoryRequest(BaseModel):
    workflow_id: str
    story: UserStory
    modified_by: str
    comments: str | None = None


class AuditEvent(BaseModel):
    action: AuditAction
    workflow_id: str
    actor: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowHistoryEvent(BaseModel):
    workflow_id: str
    from_status: PipelineStatus | None = None
    to_status: PipelineStatus
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any | None = None
    errors: list[str] = Field(default_factory=list)


def _matrix_values_for(
    matrix: list[dict[str, Any]],
    *,
    feature_id: str,
    one_line_story_id: str,
    keys: tuple[str, ...],
) -> list[str]:
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
    return list(dict.fromkeys(values))
