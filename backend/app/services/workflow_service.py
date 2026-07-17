from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
import os
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from app.orchestrator.langgraph_adapters import WorkflowStateAdapter
from app.orchestrator.langgraph_state import WorkflowState
from app.schemas.user_story import (
    GenerateUserStoriesRequest,
    ModifyStoryRequest,
    PipelineStatus,
    ReviewDecisionRequest,
    RetryUserStoriesRequest,
    UserStoryGenerationResponse,
    ValidateUserStoriesRequest,
    ValidationResult,
    UserStory,
)
from app.schemas.workflow import (
    WorkflowStartRequest,
    WorkflowStateResponse,
    WorkflowStatusResponse,
)

import logging
from app.cache.cache_service import CacheService
from app.database.repositories.implementations import WorkflowRepository
from app.agents.epic_agent_2 import EpicGenerationAgent, Epic
from app.agents.user_story_agent import UserStoryGenerationAgent
from app.database.redis.cache import cache_epics, get_cached_epics

logger = logging.getLogger(__name__)

class WorkflowStateNotFoundError(RuntimeError):
    pass


WorkflowRunnerFactory = Callable[[], Any]


class WorkflowApiService:
    """Service facade for running and retrieving LangGraph workflow state."""

    def __init__(
        self,
        *,
        workflow_runner_factory: WorkflowRunnerFactory | None = None,
        workflow_repository: Optional[WorkflowRepository] = None,
        cache_service: Optional[CacheService] = None,
        redis_client: Any | None = None,
        epic_agent: EpicGenerationAgent | None = None,
    ) -> None:
        self._workflow_runner_factory = workflow_runner_factory or self._default_runner
        self.workflow_repository = workflow_repository
        self.cache = cache_service
        self.redis = redis_client
        self.epic_agent = epic_agent
        self._states: dict[str, WorkflowState] = {} # Fallback memory dict if no DB injected

    def _default_runner(self) -> Any:
        from app.orchestrator.langgraph_workflow import LangGraphWorkflow
        enable_nlp_rag = os.getenv("ENABLE_NLP_RAG", "false").lower() == "true"
        return LangGraphWorkflow(
            enable_human_review_hook=True,
            enable_nlp_rag_hook=enable_nlp_rag,
        )

    async def execute_story_generation(self, request: GenerateUserStoriesRequest) -> UserStoryGenerationResponse:
        state = await self._execute_story_workflow(request)
        _record_artifact_versions(state, "story", state.get("user_stories", []), "AI Generator", "Generated")
        await self._save_state(request.workflow_id, state)
        return self._story_generation_response(state)

    async def execute_story_validation(self, request: ValidateUserStoriesRequest) -> ValidationResult:
        state = await self._execute_story_workflow(request)
        return self._validation_result(state)

    async def execute_story_retry(self, request: RetryUserStoriesRequest) -> UserStoryGenerationResponse:
        state = await self._get_state_data(request.workflow_id) or {}
        state_story_values = list(state.get("user_stories", []))
        if self.workflow_repository:
            from sqlalchemy import text

            largest_story_state = await self.workflow_repository.session.scalar(
                text(
                    "SELECT state_data FROM workflow_states "
                    "WHERE workflow_id = :workflow_id "
                    "AND jsonb_typeof(state_data::jsonb -> 'user_stories') = 'array' "
                    "ORDER BY jsonb_array_length(state_data::jsonb -> 'user_stories') DESC, "
                    "version DESC LIMIT 1"
                ),
                {"workflow_id": request.workflow_id},
            )
            if isinstance(largest_story_state, dict) and len(largest_story_state.get("user_stories", [])) > len(state_story_values):
                state_story_values = list(largest_story_state["user_stories"])
        request_story_by_id = {story.id: story for story in request.previous_stories}
        previous_values = [
            request_story_by_id.get(str(_json_safe(story).get("id")), story)
            for story in state_story_values
        ] or list(request.previous_stories)
        previous = [
            story if isinstance(story, UserStory) else UserStory(**story)
            for story in previous_values
        ]
        failed_ids = list(
            dict.fromkeys(
                issue.story_id
                for issue in request.validation_issues
                if issue.story_id
            )
        ) or [story.id for story in previous]
        # A retry is also a valid standalone API operation. When no persisted
        # workflow exists yet, build its generation context from the request
        # instead of trying to adapt an empty state (which drops chunks and
        # fails GenerateUserStoriesRequest validation).
        try:
            retry_payload = (
                WorkflowStateAdapter().generation_request_from_state(state)
                if state
                else None
            )
        except ValueError:
            retry_payload = None
        if retry_payload is None:
            retry_payload = GenerateUserStoriesRequest.model_validate(
                request.model_dump()
            )
        feedback = " ".join(
            issue.message.strip()
            for issue in request.validation_issues
            if issue.story_id in set(failed_ids) and issue.message.strip()
        )
        traceability = dict(retry_payload.traceability)
        if feedback:
            traceability["regeneration_feedback"] = feedback
        retry_payload = retry_payload.model_copy(
            update={
                "workflow_id": request.workflow_id,
                "max_retry_attempts": request.max_retry_attempts,
                "traceability": traceability,
            }
        )
        regenerated = await UserStoryGenerationAgent().regenerate_failed_stories(
            retry_payload,
            previous,
            failed_ids,
        )
        state.update(
            {
                "workflow_id": request.workflow_id,
                "workflow_status": "REVIEW_REQUIRED",
                "review_required": True,
                "retry_count": request.retry_attempt,
                "user_stories": regenerated,
            }
        )
        changed = [story for story in regenerated if story.id in set(failed_ids)]
        _record_artifact_versions(state, "story", changed, "AI Generator", "Regenerated")
        await self._save_state(request.workflow_id, state)
        return self._story_generation_response(state)

    async def execute_story_review(self, request: ReviewDecisionRequest) -> UserStoryGenerationResponse:
        state = await self._execute_story_workflow(request)
        return self._story_generation_response(state)

    async def execute_story_modify(self, request: ModifyStoryRequest) -> UserStoryGenerationResponse:
        state = await self._get_state_data(request.workflow_id)
        if state is None:
            raise WorkflowStateNotFoundError(f"Workflow '{request.workflow_id}' was not found.")
        stories = [_json_safe(story) for story in state.get("user_stories", [])]
        replacement = request.story.model_dump(mode="json")
        
        # Recalculate confidence score for modified story
        try:
            from app.confidence.confidence_service import ConfidenceService
            from app.schemas.user_story import ValidationIssue
            cs = ConfidenceService()
            validation_data = state.get("validation") or state.get("validation_result") or {}
            issues = []
            if isinstance(validation_data, dict):
                raw_issues = validation_data.get("issues", [])
                for issue in raw_issues:
                    try:
                        issues.append(ValidationIssue(**issue))
                    except Exception:
                        pass
            elif hasattr(validation_data, "issues"):
                issues = validation_data.issues
            replacement["confidence_score"] = cs.calculate_story(request.story, issues)
        except Exception as e:
            logger.warning("Could not recalculate modified story confidence score: %s", e)

        index = next((i for i, story in enumerate(stories) if story.get("id") == request.story.id), None)
        if index is None:
            raise WorkflowStateNotFoundError(f"Story '{request.story.id}' was not found.")
        stories[index] = replacement
        state["user_stories"] = stories
        state["workflow_status"] = "REVIEW_REQUIRED"
        state["review_required"] = True
        _record_artifact_versions(
            state,
            "story",
            [replacement],
            request.modified_by,
            request.comments or "Modified",
        )
        await self._save_state(request.workflow_id, state)
        return self._story_generation_response(state)

    async def start(self, request: WorkflowStartRequest) -> WorkflowStateResponse:
        import asyncio
        state = self._initial_state(request)
        await self._save_state(request.workflow_id, state)
        
        try:
            final_state = await self._workflow_runner_factory().run_workflow(state)
        except asyncio.CancelledError:
            state["workflow_status"] = "CANCELLED"
            await self._save_state(request.workflow_id, state)
            raise
        except Exception:
            await self._save_state(request.workflow_id, state)
            raise

        _record_artifact_versions(final_state, "epic", final_state.get("epics", []), "AI Generator", "Generated")
        _record_artifact_versions(final_state, "feature", final_state.get("features", []), "AI Generator", "Generated")
        _record_artifact_versions(final_state, "story", final_state.get("user_stories", []), "AI Generator", "Generated")
        await self._save_state(request.workflow_id, final_state)
        return self._state_response(final_state)

    async def set_state(
        self,
        workflow_id: str,
        *,
        workflow_status: str | None = None,
        **updates: Any,
    ) -> WorkflowStateResponse:
        state = await self._get_state_data(workflow_id)
        if state is None:
            state = {
                "workflow_id": workflow_id,
                "workflow_status": workflow_status or "PENDING",
                "errors": [],
                "failed_node": None,
                "last_error": None,
            }
        
        if workflow_status is not None:
            state["workflow_status"] = workflow_status
        for key, value in updates.items():
            state[key] = value
            
        await self._save_state(workflow_id, state)
        return self._state_response(state)

    async def get(self, workflow_id: str) -> WorkflowStateResponse:
        state = await self._get_state_data(workflow_id)
        if state is None:
            raise WorkflowStateNotFoundError(f"Workflow '{workflow_id}' was not found.")
        return self._state_response(state)

    async def get_story_generation(self, workflow_id: str) -> UserStoryGenerationResponse:
        state = await self._get_state_data(workflow_id)
        if state is None:
            raise WorkflowStateNotFoundError(f"Workflow '{workflow_id}' was not found.")
        return self._story_generation_response(state)

    async def status(self, workflow_id: str) -> WorkflowStatusResponse:
        state = await self._get_state_data(workflow_id)
        if state is None:
            raise WorkflowStateNotFoundError(f"Workflow '{workflow_id}' was not found.")
            
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            workflow_status=state.get("workflow_status", "UNKNOWN"),
            failed_node=state.get("failed_node"),
            last_error=_json_safe(state.get("last_error")),
            errors=_json_safe(state.get("errors", [])),
        )

    async def regenerate_epic(
        self,
        workflow_id: str,
        epic_id: str,
        feedback: str = "",
    ) -> dict[str, Any]:
        """Regenerate one epic while preserving the remainder of the plan."""
        state = await self._get_state_data(workflow_id)
        if state is None:
            raise WorkflowStateNotFoundError(f"Workflow '{workflow_id}' was not found.")

        epics = [_json_safe(epic) for epic in state.get("epics", [])]
        project_id = str(state.get("project_id") or workflow_id)
        user_id = str((state.get("metadata") or {}).get("user_id") or "default")

        # Redis is the latest planning snapshot when available. The workflow
        # state remains the durable fallback and is used to warm an empty cache.
        if self.redis is not None:
            try:
                cached = await get_cached_epics(self.redis, user_id, project_id)
                if cached:
                    epics = cached
                else:
                    await cache_epics(self.redis, user_id, project_id, epics)
            except Exception as exc:
                logger.warning("Failed to read epic planning cache: %s", exc)

        selected_index = next(
            (index for index, epic in enumerate(epics) if _epic_id(epic) == epic_id),
            None,
        )
        if selected_index is None:
            raise WorkflowStateNotFoundError(f"Epic '{epic_id}' was not found.")

        previous = epics[selected_index]
        assigned_features = _epic_features(previous, state, epic_id)
        payload = {
            "task": "Regenerate only this epic using its assigned capabilities.",
            "selected_epic": previous,
            "assigned_functional_requirements": assigned_features,
            "feedback": feedback.strip(),
            "constraints": [
                "Return exactly one epic.",
                "Do not add, remove, or invent assigned requirements.",
                "Use a concise business-oriented title and one-line story.",
            ],
        }

        replacement: dict[str, Any] | None = None
        epic_agent = self.epic_agent or EpicGenerationAgent()
        for _attempt in range(2):
            generated = await epic_agent.execute(payload)
            if not generated.epics:
                continue
            candidate = generated.epics[0]
            candidate.epic_id = epic_id
            if not _same_feature_scope(candidate.features, assigned_features):
                continue
            normalized = _merge_regenerated_epic(previous, candidate)
            if not _same_epic_content(previous, normalized):
                replacement = normalized
                break
            payload["constraints"].append(
                "The prior attempt was identical; improve the title or one-line story without changing scope."
            )

        no_alternative = replacement is None
        replacement = previous if no_alternative else replacement
        replacement = dict(replacement)
        replacement["metadata"] = {
            **dict(replacement.get("metadata") or {}),
            "regeneration_status": (
                "no meaningful alternative found" if no_alternative else "regenerated"
            ),
        }

        updated_epics = list(epics)
        updated_epics[selected_index] = replacement
        state["epics"] = updated_epics
        _record_artifact_versions(
            state,
            "epic",
            [replacement],
            "AI Generator",
            "Regenerated" if not no_alternative else "Regeneration attempted",
        )
        await self._save_state(workflow_id, state)
        if self.redis is not None:
            try:
                await cache_epics(self.redis, user_id, project_id, updated_epics)
            except Exception as exc:
                logger.warning("Failed to update epic planning cache: %s", exc)
        return replacement

    async def undo_artifact(
        self,
        workflow_id: str,
        entity_type: str,
        entity_id: str,
        target_version: int,
    ) -> dict[str, Any]:
        """Undo an artifact to a previous version."""
        state = await self._get_state_data(workflow_id)
        if state is None:
            raise WorkflowStateNotFoundError(f"Workflow '{workflow_id}' was not found.")

        versions = state.get("artifact_versions", [])
        
        # Find the target version snapshot
        target_record = next(
            (r for r in versions if r.get("entityType") == entity_type and r.get("entityId") == entity_id and r.get("version") == f"v{target_version}"),
            None
        )
        if not target_record:
            raise WorkflowStateNotFoundError(f"Version v{target_version} not found for {entity_type} '{entity_id}'.")

        snapshot = dict(target_record["snapshot"])
        
        # Update the state based on entity_type
        if entity_type == "epic":
            epics = list(state.get("epics", []))
            index = next((i for i, e in enumerate(epics) if _epic_id(e) == entity_id), None)
            if index is not None:
                epics[index] = snapshot
            state["epics"] = epics
        elif entity_type == "story":
            stories = list(state.get("user_stories", []))
            index = next((i for i, s in enumerate(stories) if s.get("id") == entity_id), None)
            if index is not None:
                stories[index] = snapshot
            state["user_stories"] = stories
        else:
            raise ValueError(f"Undo not supported for entity type: {entity_type}")

        # Drop versions newer than the target version for this entity to revert version number
        new_versions = []
        for v in versions:
            if v.get("entityType") == entity_type and str(v.get("entityId")) == str(entity_id):
                v_num_str = str(v.get("version", "")).replace("v", "")
                if v_num_str.isdigit() and int(v_num_str) > target_version:
                    continue  # Drop versions newer than the target
            new_versions.append(v)
        state["artifact_versions"] = new_versions

        await self._save_state(workflow_id, state)
        return snapshot

    async def update_state_partial(self, workflow_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        state = await self._get_state_data(workflow_id)
        if state is None:
            raise WorkflowStateNotFoundError(f"Workflow '{workflow_id}' was not found.")
        for k, v in updates.items():
            state[k] = v
        await self._save_state(workflow_id, state)
        return {"status": "success"}

    async def _get_state_data(self, workflow_id: str) -> Optional[WorkflowState]:
        # 1. Read Cache First
        if self.cache:
            try:
                cached_state = await self.cache.get_workflow_state(workflow_id)
                if cached_state:
                    return cached_state
            except Exception as e:
                logger.warning("Failed to read workflow state from cache: %s", e)

        # 2. Use Database if cache miss
        if self.workflow_repository:
            from sqlalchemy import select
            from app.database.models import WorkflowStateModel

            latest_state = await self.workflow_repository.session.scalar(
                select(WorkflowStateModel)
                .where(WorkflowStateModel.workflow_id == workflow_id)
                .order_by(WorkflowStateModel.version.desc())
                .limit(1)
            )
            if latest_state is not None:
                state_data = latest_state.state_data
                
                # Update cache after DB read
                if self.cache:
                    try:
                        await self.cache.set_workflow_state(workflow_id, state_data)
                    except Exception as e:
                        logger.warning("Failed to refresh workflow state cache: %s", e)
                return state_data

        # 3. Fallback memory dict (legacy/testing)
        return self._states.get(workflow_id)
        
    async def _save_state(self, workflow_id: str, state: WorkflowState) -> None:
        # 1. Save to dict (fallback)
        self._states[workflow_id] = state
        
        # 2. Save to DB (PostgreSQL is the ONLY source of truth)
        if self.workflow_repository:
            # We fetch workflow or create it
            workflow = await self.workflow_repository.get(workflow_id)
            if not workflow:
                from app.database.models import Workflow
                workflow = await self.workflow_repository.create(
                    obj_in={
                        "id": workflow_id,
                        "status": state.get("workflow_status", "PENDING"),
                        "document_id": state.get("document_id"),
                        "project_id": state.get("project_id"),
                    }
                )
                version = 1
            else:
                from sqlalchemy import func, select
                from app.database.models import WorkflowStateModel
                latest_version = await self.workflow_repository.session.scalar(
                    select(func.max(WorkflowStateModel.version)).where(
                        WorkflowStateModel.workflow_id == workflow_id
                    )
                )
                version = int(latest_version or 0) + 1
                
            # Add state record
            from app.database.models import WorkflowStateModel
            state_model = WorkflowStateModel(
                workflow_id=workflow.id,
                version=version,
                current_node=state.get("current_node", "UNKNOWN"),
                state_data=_json_safe(state)
            )
            self.workflow_repository.session.add(state_model)
            await self.workflow_repository.session.flush()
            workflow.status = str(state.get("workflow_status", workflow.status))
            await self.workflow_repository.session.commit()

        # 3. Update Cache ONLY after successful database commit
        if self.cache:
            try:
                await self.cache.set_workflow_state(workflow_id, _json_safe(state))
            except Exception as e:
                logger.warning("Failed to update workflow state cache: %s", e)

    async def _execute_story_workflow(self, request: Any) -> WorkflowState:
        workflow_id = getattr(request, "workflow_id", None)
        existing_state = await self._get_state_data(workflow_id) if workflow_id else None
        
        adapter = WorkflowStateAdapter()
        new_state = adapter.story_request_to_state(request) if hasattr(adapter, "story_request_to_state") else {
            "workflow_id": workflow_id,
            "workflow_status": "RUNNING",
        }
        
        if existing_state:
            state = dict(existing_state)
            for k, v in new_state.items():
                if v or k in {"workflow_status", "workflow_id", "confidence_threshold", "max_retry_attempts"}:
                    state[k] = v
            state["workflow_status"] = "RUNNING"
        else:
            state = new_state
            
        await self._save_state(workflow_id, state)
        
        try:
            final_state = await self._workflow_runner_factory().run_workflow(state)
        except Exception:
            await self._save_state(workflow_id, state)
            raise
            
        await self._save_state(workflow_id, final_state)
        return final_state

    def _initial_state(self, request: WorkflowStartRequest) -> WorkflowState:
        state: WorkflowState = {
            "workflow_id": request.workflow_id,
            "workflow_status": "PENDING",
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
            "file_path": request.file_path,
            "confidence_threshold": request.confidence_threshold,
            "max_retry_attempts": request.max_retry_attempts,
            "metadata": request.metadata,
        }
        if request.document_id is not None:
            state["document_id"] = request.document_id
        if request.project_id is not None:
            state["project_id"] = request.project_id
        return state

    def _state_response(self, state: WorkflowState) -> WorkflowStateResponse:
        workflow_id = state.get("workflow_id")
        if workflow_id is None:
            raise ValueError("Workflow state is missing workflow_id.")
        return WorkflowStateResponse(
            workflow_id=workflow_id,
            workflow_status=state.get("workflow_status", "UNKNOWN"),
            state=_json_safe(state),
        )

    def _story_generation_response(self, state: WorkflowState) -> UserStoryGenerationResponse:
        validation_result = self._validation_result(state)
        stories = list(state.get("user_stories", []))
        workflow_status = state.get("workflow_status", "COMPLETED")
        status = self._pipeline_status_for(state, validation_result)
        return UserStoryGenerationResponse(
            workflow_id=state.get("workflow_id", "UNKNOWN"),
            status=status,
            stories=stories,
            user_stories=stories,
            traceability_links=[],
            generation_metadata={
                "generated_story_count": len(stories),
                "workflow_status": workflow_status,
                "langgraph_execution": True,
            },
            confidence_score=validation_result.confidence_score,
            validation=validation_result,
            retry_attempts=int(state.get("retry_count", 0)),
            review_required=bool(state.get("review_required", False)),
            audit_trail=[],
            workflow_history=[],
        )

    def _validation_result(self, state: WorkflowState) -> ValidationResult:
        validation_result = state.get("validation") or state.get("validation_result")
        if validation_result is None:
            return ValidationResult(
                validation_status=PipelineStatus.VALIDATION_PASSED,
                passed=True,
                confidence_score=0.0,
                threshold=0.8,
            )
        if isinstance(validation_result, dict):
            return ValidationResult(**validation_result)
        return validation_result

    @staticmethod
    def _pipeline_status_for(state: WorkflowState, validation_result: ValidationResult) -> PipelineStatus:
        if state.get("workflow_status") == "RETRY_REQUIRED":
            return PipelineStatus.RETRY_REQUIRED
        if state.get("review_required"):
            return PipelineStatus.REVIEW_REQUIRED
        if validation_result.review_required:
            return PipelineStatus.REVIEW_REQUIRED
        if validation_result.retry_required:
            return PipelineStatus.RETRY_REQUIRED
        if validation_result.passed:
            return PipelineStatus.VALIDATION_PASSED
        return PipelineStatus.VALIDATION_FAILED


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _record_artifact_versions(
    state: WorkflowState,
    entity_type: str,
    artifacts: list[Any],
    author: str,
    changes: str,
) -> None:
    records = list(state.get("artifact_versions", []))
    for artifact_value in artifacts:
        artifact = _json_safe(artifact_value)
        entity_id = str(artifact.get("id") or artifact.get(f"{entity_type}_id") or "")
        if not entity_id:
            continue
        version = 1 + sum(
            1
            for record in records
            if record.get("entityType") == entity_type and record.get("entityId") == entity_id
        )
        records.append(
            {
                "id": f"{entity_type}-{entity_id}-v{version}",
                "version": f"v{version}",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "entityId": entity_id,
                "entityType": entity_type,
                "author": author,
                "changes": changes,
                "snapshot": artifact,
            }
        )
    state["artifact_versions"] = records


def _epic_id(epic: dict[str, Any]) -> str:
    return str(epic.get("id") or epic.get("epic_id") or "")


def _epic_features(
    epic: dict[str, Any],
    state: WorkflowState,
    epic_id: str,
) -> list[str]:
    metadata_features = list((epic.get("metadata") or {}).get("features") or [])
    if metadata_features:
        return [str(feature).strip() for feature in metadata_features if str(feature).strip()]
    return [
        str(feature.get("name") or feature.get("title") or "").strip()
        for feature in map(_json_safe, state.get("features", []))
        if str((feature.get("metadata") or {}).get("epic_id") or feature.get("epic_id") or "") == epic_id
        and str(feature.get("name") or feature.get("title") or "").strip()
    ]


def _canonical(value: Any) -> str:
    return " ".join(str(value or "").casefold().split()).rstrip(".")


def _same_feature_scope(candidate: list[str], assigned: list[str]) -> bool:
    return sorted(_canonical(item) for item in candidate) == sorted(
        _canonical(item) for item in assigned
    )


def _same_epic_content(previous: dict[str, Any], candidate: dict[str, Any]) -> bool:
    previous_metadata = previous.get("metadata") or {}
    candidate_metadata = candidate.get("metadata") or {}
    return (
        _canonical(previous.get("name") or previous.get("title"))
        == _canonical(candidate.get("name") or candidate.get("title"))
        and _canonical(previous_metadata.get("one_line_story") or previous.get("one_line_story"))
        == _canonical(candidate_metadata.get("one_line_story") or candidate.get("one_line_story"))
        and _same_feature_scope(
            list(candidate_metadata.get("features") or candidate.get("features") or []),
            list(previous_metadata.get("features") or previous.get("features") or []),
        )
    )


def _merge_regenerated_epic(previous: dict[str, Any], candidate: Epic) -> dict[str, Any]:
    updated = dict(previous)
    metadata = dict(previous.get("metadata") or {})
    original_id = _epic_id(previous)
    
    if "name" in previous or "title" in previous or "id" in previous:
        updated["id"] = original_id
        updated["epic_id"] = original_id
        updated["name"] = candidate.title
        updated["title"] = candidate.title
        metadata.update(
            {
                "priority": candidate.priority,
                "dependencies": candidate.dependencies,
                "features": candidate.features,
                "one_line_story": candidate.one_line_story,
            }
        )
        updated["metadata"] = metadata
    else:
        updated.update(
            {
                "id": original_id,
                "epic_id": original_id,
                "title": candidate.title,
                "name": candidate.title,
                "features": candidate.features,
                "one_line_story": candidate.one_line_story,
                "dependencies": candidate.dependencies,
                "priority": candidate.priority,
            }
        )
    return updated
