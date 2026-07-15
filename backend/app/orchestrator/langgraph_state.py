from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict
from uuid import UUID

from app.schemas import Chunk
from app.schemas.user_story import (
    Agent1Output,
    Agent2Output,
    GenerateUserStoriesRequest,
    OneLineStoryInput,
    PlanningArtifact,
    RetrievedChunk,
    UserStory,
    UserStoryGenerationResponse,
    ValidationResult,
)


class WorkflowState(TypedDict, total=False):
    """Shared state passed between LangGraph workflow nodes."""

    workflow_id: str
    workflow_status: str
    errors: list[dict[str, Any]]
    failed_node: str | None
    last_error: dict[str, Any] | None
    current_node: str | None
    completed_nodes: list[str]
    failed_nodes: list[str]
    retry_count: int
    retry_reason: str | None
    retry_status: str | None
    retry_history: list[dict[str, Any]]
    review_required: bool
    review_status: str | None
    approval_status: str | None
    execution_history: list[dict[str, Any]]
    workflow_progress: int
    warnings: list[str]
    node_execution_log: list[dict[str, Any]]
    audit_log: list[dict[str, Any]]
    execution_time: float | None
    file_path: str | Path
    document_id: UUID | str
    project_id: UUID | str
    confidence_threshold: float
    max_retry_attempts: int

    parsed_text: str
    chunks: list[Chunk]
    labeled_chunks: list[Chunk]
    retrieved_chunks: list[RetrievedChunk]

    requirement_chunks: list[dict[str, Any]]
    requirement_analysis: dict[str, Any]
    agent1_output: Agent1Output

    epic_generation: Any
    epics: list[PlanningArtifact]
    features: list[PlanningArtifact]
    one_line_stories: list[OneLineStoryInput]
    traceability: dict[str, Any]
    agent2_output: Agent2Output

    generation_request: GenerateUserStoriesRequest
    user_stories: list[UserStory]
    generation_response: UserStoryGenerationResponse
    validation_result: ValidationResult

    guardrails: dict[str, Any]
    rag_context: dict[str, Any]
    human_review: dict[str, Any]
    metadata: dict[str, Any]
