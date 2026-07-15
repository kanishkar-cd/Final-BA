from __future__ import annotations

from app.schemas.user_story import (
    GenerateUserStoriesRequest,
    ModifyStoryRequest,
    RetryUserStoriesRequest,
    ReviewDecisionRequest,
    ValidateUserStoriesRequest,
    ValidationResult,
    UserStoryGenerationResponse,
)
from app.services.workflow_service import WorkflowApiService


class UserStoryOrchestrator:
    def __init__(
        self,
        *,
        workflow_api_service: WorkflowApiService,
    ) -> None:
        self._workflow_api_service = workflow_api_service

    async def run_from_planning_output(self, request: GenerateUserStoriesRequest) -> UserStoryGenerationResponse:
        await self._record_story_workflow(request.workflow_id, "RUNNING", operation="generate")
        try:
            response = await self._workflow_api_service.execute_story_generation(request)
        except Exception as exc:
            await self._record_story_workflow(
                request.workflow_id,
                "FAILED",
                operation="generate",
                last_error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            raise
        await self._record_story_workflow(
            request.workflow_id,
            self._workflow_status_for(response),
            operation="generate",
            response=response,
        )
        return response

    async def run_from_agent_outputs(self, request: GenerateUserStoriesRequest) -> UserStoryGenerationResponse:
        return await self._workflow_api_service.execute_story_generation(request)

    async def retry(self, request: RetryUserStoriesRequest) -> UserStoryGenerationResponse:
        try:
            return await self._workflow_api_service.execute_story_retry(request)
        except Exception as exc:
            await self._record_story_workflow(
                request.workflow_id,
                "FAILED",
                operation="retry",
                last_error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            raise

    async def validate(self, request: ValidateUserStoriesRequest) -> ValidationResult:
        await self._record_story_workflow(request.workflow_id, "RUNNING", operation="validate")
        try:
            validation = await self._workflow_api_service.execute_story_validation(request)
        except Exception as exc:
            await self._record_story_workflow(
                request.workflow_id,
                "FAILED",
                operation="validate",
                last_error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            raise
        await self._record_story_workflow(
            request.workflow_id,
            self._workflow_status_for(validation),
            operation="validate",
            response=validation,
        )
        return validation

    async def modify_story(self, request: ModifyStoryRequest) -> UserStoryGenerationResponse:
        await self._record_story_workflow(request.workflow_id, "RUNNING", operation="modify")
        try:
            response = await self._workflow_api_service.execute_story_modify(request)
        except Exception as exc:
            await self._record_story_workflow(
                request.workflow_id,
                "FAILED",
                operation="modify",
                last_error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            raise
        await self._record_story_workflow(
            request.workflow_id,
            self._workflow_status_for(response),
            operation="modify",
            response=response,
        )
        return response

    async def review(self, request: ReviewDecisionRequest) -> UserStoryGenerationResponse:
        await self._record_story_workflow(request.workflow_id, "RUNNING", operation="review")
        try:
            response = await self._workflow_api_service.execute_story_review(request)
        except Exception as exc:
            await self._record_story_workflow(
                request.workflow_id,
                "FAILED",
                operation="review",
                last_error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            raise
        await self._record_story_workflow(
            request.workflow_id,
            self._workflow_status_for(response),
            operation="review",
            response=response,
        )
        return response

    async def get(self, workflow_id: str) -> UserStoryGenerationResponse:
        return await self._workflow_api_service.get_story_generation(workflow_id)

    async def _record_story_workflow(self, workflow_id: str | None, workflow_status: str, **updates: object) -> None:
        if not workflow_id:
            return
        if hasattr(self._workflow_api_service, "set_state"):
            await self._workflow_api_service.set_state(workflow_id, workflow_status=workflow_status, **updates)

    @staticmethod
    def _workflow_status_for(response: object) -> str:
        if hasattr(response, "status") and getattr(response, "status") is not None:
            value = getattr(response, "status")
            return value.value if hasattr(value, "value") else str(value)
        if hasattr(response, "validation_status") and getattr(response, "validation_status") is not None:
            value = getattr(response, "validation_status")
            return value.value if hasattr(value, "value") else str(value)
        return "COMPLETED"
