from __future__ import annotations

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.story_router import get_user_story_workflow
from app.orchestrator.user_story_orchestrator import UserStoryOrchestrator
from app.schemas.user_story import GenerateUserStoriesRequest, PipelineStatus, UserStoryGenerationResponse
from app.schemas.workflow import WorkflowStateResponse


class FakeWorkflowApiService:
    def __init__(self) -> None:
        self.received_states: list[dict] = []

    async def execute_story_generation(self, request: GenerateUserStoriesRequest) -> UserStoryGenerationResponse:
        from app.schemas.user_story import UserStoryGenerationResponse
        state_dict = request.model_dump()
        self.received_states.append(state_dict)
        return UserStoryGenerationResponse(
            workflow_id=request.workflow_id,
            status=PipelineStatus.VALIDATION_PASSED,
            stories=[],
            user_stories=[],
            validation={
                "validation_status": PipelineStatus.VALIDATION_PASSED,
                "passed": True,
                "confidence_score": 0.95,
                "threshold": 0.8,
                "retry_required": False,
                "review_required": False,
            },
        )


def test_generate_story_endpoint_uses_workflow_service_for_execution() -> None:
    workflow_service = FakeWorkflowApiService()
    orchestrator = UserStoryOrchestrator(workflow_api_service=workflow_service)

    request = GenerateUserStoriesRequest(
        workflow_id="WF-STORY-1",
        confidence_threshold=0.8,
        max_retry_attempts=2,
        retrieved_chunks=[],
        one_line_stories=[],
    )

    response = asyncio.run(orchestrator.run_from_planning_output(request))

    assert workflow_service.received_states
    assert workflow_service.received_states[0]["workflow_id"] == "WF-STORY-1"
    assert response.workflow_id == "WF-STORY-1"
    assert response.status == PipelineStatus.VALIDATION_PASSED


def test_get_user_story_workflow_awaits_orchestrator_result() -> None:
    class FakeOrchestrator:
        async def get(self, workflow_id: str) -> UserStoryGenerationResponse:
            return UserStoryGenerationResponse(
                workflow_id=workflow_id,
                status=PipelineStatus.APPROVED,
                stories=[],
                user_stories=[],
                validation={
                    "validation_status": PipelineStatus.APPROVED,
                    "passed": True,
                    "confidence_score": 1.0,
                    "threshold": 0.8,
                    "retry_required": False,
                    "review_required": False,
                },
            )

    response = asyncio.run(get_user_story_workflow("WF-GET-1", FakeOrchestrator()))

    assert response.data.workflow_id == "WF-GET-1"
    assert response.data.status == PipelineStatus.APPROVED


def test_record_story_workflow_awaits_set_state() -> None:
    class RecordingWorkflowApiService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, object]]] = []

        async def set_state(self, workflow_id: str, *, workflow_status: str | None = None, **updates: object) -> None:
            self.calls.append((workflow_id, workflow_status or "PENDING", updates))

    service = RecordingWorkflowApiService()
    orchestrator = UserStoryOrchestrator(workflow_api_service=service)

    asyncio.run(orchestrator._record_story_workflow("WF-STATE-1", "RUNNING", operation="generate"))

    assert service.calls == [("WF-STATE-1", "RUNNING", {"operation": "generate"})]


from unittest.mock import patch

@patch("app.shared.llm_client.LLMService.execute")
def test_direct_generation_skips_preprocessing_crash(mock_execute) -> None:
    from app.orchestrator.langgraph_workflow import LangGraphWorkflow
    from app.schemas.user_story import RetrievedChunk, PipelineStatus, PlanningArtifact, OneLineStoryInput
    
    # Mock LLM to avoid real calls
    async def mock_execute_side_effect(prompt, response_schema=None, **kwargs):
        if response_schema:
            return response_schema()
        return {}
    mock_execute.side_effect = mock_execute_side_effect 
    
    workflow = LangGraphWorkflow()
    
    state = {
        "workflow_id": "WF-INTEGRATION",
        "file_path": None,
        "retrieved_chunks": [RetrievedChunk(id="CHUNK-1", content="Test chunk", metadata={})],
        "validation_result": {"passed": True, "confidence_score": 1.0},
        "epics": [PlanningArtifact(id="EPIC-1", name="Epic 1")],
        "features": [PlanningArtifact(id="FEAT-1", name="Feature 1")],
        "one_line_stories": [OneLineStoryInput(id="OLS-1", feature_id="FEAT-1", epic_id="EPIC-1", summary="OLS", chunk_refs=["CHUNK-1"])],
    }
    
    # Should not raise ValueError for missing file_path
    try:
        final_state = asyncio.run(workflow.run_workflow(state))
        assert final_state.get("workflow_status") in ("COMPLETED", "FAILED")
    except ValueError as e:
        if "file_path is required" in str(e):
            raise AssertionError("Preprocessing crashed due to missing file_path!") from e
        raise

