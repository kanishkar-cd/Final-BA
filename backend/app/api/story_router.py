from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_user_story_orchestrator
from app.orchestrator.user_story_orchestrator import UserStoryOrchestrator
from app.schemas.user_story import (
    ApiResponse,
    GenerateUserStoriesRequest,
    ModifyStoryRequest,
    RetryUserStoriesRequest,
    ReviewDecisionRequest,
    UserStoryGenerationResponse,
    ValidateUserStoriesRequest,
    ValidationResult,
)
from app.services.workflow_service import WorkflowStateNotFoundError


router = APIRouter(prefix="/user-stories", tags=["User Story Pipeline"])


@router.post("/generate", response_model=ApiResponse)
async def generate_user_stories(
    request: GenerateUserStoriesRequest,
    orchestrator: UserStoryOrchestrator = Depends(get_user_story_orchestrator),
) -> ApiResponse:
    response = await orchestrator.run_from_planning_output(request)
    return _ok("User stories generated and validated.", response)


@router.post("/validate", response_model=ApiResponse)
async def validate_user_stories(
    request: ValidateUserStoriesRequest,
    orchestrator: UserStoryOrchestrator = Depends(get_user_story_orchestrator),
) -> ApiResponse:
    validation = await orchestrator.validate(request)
    return _ok("User story validation completed.", validation)


@router.post("/retry", response_model=ApiResponse)
async def retry_user_story_generation(
    request: RetryUserStoriesRequest,
    orchestrator: UserStoryOrchestrator = Depends(get_user_story_orchestrator),
) -> ApiResponse:
    response = await orchestrator.retry(request)
    return _ok("User story retry completed.", response)


@router.post("/review/modify", response_model=ApiResponse)
async def modify_user_story(
    request: ModifyStoryRequest,
    orchestrator: UserStoryOrchestrator = Depends(get_user_story_orchestrator),
) -> ApiResponse:
    try:
        response = await orchestrator.modify_story(request)
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc
    return _ok("User story modification recorded.", response)


@router.post("/review/decision", response_model=ApiResponse)
async def review_user_stories(
    request: ReviewDecisionRequest,
    orchestrator: UserStoryOrchestrator = Depends(get_user_story_orchestrator),
) -> ApiResponse:
    try:
        response = await orchestrator.review(request)
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc
    return _ok("Human review decision recorded.", response)


@router.post("/review/approve", response_model=ApiResponse)
async def approve_user_stories(
    request: ReviewDecisionRequest,
    orchestrator: UserStoryOrchestrator = Depends(get_user_story_orchestrator),
) -> ApiResponse:
    approved_request = request.model_copy(update={"approved": True})
    try:
        response = await orchestrator.review(approved_request)
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc
    return _ok("User stories approved.", response)


@router.get("/{workflow_id}", response_model=ApiResponse)
async def get_user_story_workflow(
    workflow_id: str,
    orchestrator: UserStoryOrchestrator = Depends(get_user_story_orchestrator),
) -> ApiResponse:
    try:
        response = await orchestrator.get(workflow_id)
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc
    return _ok("Workflow retrieved.", response)


def _ok(message: str, data: UserStoryGenerationResponse | ValidationResult) -> ApiResponse:
    return ApiResponse(success=True, message=message, data=data)


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
