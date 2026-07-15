from __future__ import annotations

from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import get_workflow_api_service
from app.api.workflow_router import router
from app.schemas.workflow import (
    WorkflowStartRequest,
    WorkflowStateResponse,
    WorkflowStatusResponse,
)
from app.services.workflow_service import WorkflowStateNotFoundError


class FakeWorkflowApiService:
    async def start(self, request: WorkflowStartRequest) -> WorkflowStateResponse:
        import asyncio
        from app.shared.llm_client import LLMServiceAuthenticationError, LLMServiceConfigurationError
        file_path_str = str(request.file_path)
        if "cancel" in file_path_str:
            raise asyncio.CancelledError()
        if "invalid_key" in file_path_str:
            raise LLMServiceAuthenticationError("API key is invalid (401 Unauthorized).")
        if "missing_key" in file_path_str:
            raise LLMServiceConfigurationError("API key is missing.")
        if "nested_key" in file_path_str:
            inner = LLMServiceConfigurationError("API key is missing.")
            raise Exception("Context labeling failed while invoking the LLM.") from inner
        if "nonexistent" in file_path_str:
            raise FileNotFoundError(f"Document not found: {request.file_path}")
        return WorkflowStateResponse(
            workflow_id=request.workflow_id,
            workflow_status="COMPLETED",
            state={
                "workflow_id": request.workflow_id,
                "workflow_status": "COMPLETED",
                "file_path": str(request.file_path),
            },
        )

    async def get(self, workflow_id: str) -> WorkflowStateResponse:
        if workflow_id == "missing":
            raise WorkflowStateNotFoundError("Workflow 'missing' was not found.")
        return WorkflowStateResponse(
            workflow_id=workflow_id,
            workflow_status="COMPLETED",
            state={"workflow_id": workflow_id, "workflow_status": "COMPLETED"},
        )

    async def status(self, workflow_id: str) -> WorkflowStatusResponse:
        if workflow_id == "missing":
            raise WorkflowStateNotFoundError("Workflow 'missing' was not found.")
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            workflow_status="COMPLETED",
        )


def make_client(raise_server_exceptions: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_workflow_api_service] = FakeWorkflowApiService

    from fastapi.responses import JSONResponse
    from app.shared.llm_client import LLMServiceAuthenticationError, LLMServiceConfigurationError

    def find_cause(exc: BaseException | None, target_types: tuple[type[BaseException], ...]) -> BaseException | None:
        current = exc
        while current is not None:
            if isinstance(current, target_types):
                return current
            current = current.__cause__ or current.__context__
        return None

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_exception_handler(request, exc):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(LLMServiceAuthenticationError)
    async def llm_service_auth_exception_handler(request, exc):
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
        )

    @app.exception_handler(LLMServiceConfigurationError)
    async def llm_service_config_exception_handler(request, exc):
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        auth_cause = find_cause(exc, (LLMServiceAuthenticationError, LLMServiceConfigurationError))
        if auth_cause is not None:
            return JSONResponse(
                status_code=401,
                content={"detail": str(auth_cause)},
            )
        return JSONResponse(
            status_code=500,
            content={"detail": "Unexpected error."},
        )

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_start_workflow_returns_workflow_state_response() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "sample.txt",
            "confidence_threshold": 0.8,
        },
    )

    assert response.status_code == 200
    assert response.json()["workflow_id"] == "WF-API"
    assert response.json()["workflow_status"] == "COMPLETED"
    assert response.json()["state"]["file_path"] == "sample.txt"


def test_get_workflow_returns_stored_state() -> None:
    response = make_client().get("/workflow/WF-API")

    assert response.status_code == 200
    assert response.json()["workflow_id"] == "WF-API"
    assert response.json()["state"]["workflow_status"] == "COMPLETED"


def test_get_workflow_status_returns_status_summary() -> None:
    response = make_client().get("/workflow/WF-API/status")

    assert response.status_code == 200
    assert response.json() == {
        "workflow_id": "WF-API",
        "workflow_status": "COMPLETED",
        "failed_node": None,
        "last_error": None,
        "errors": [],
    }


def test_workflow_endpoints_return_404_for_missing_workflow() -> None:
    response = make_client().get("/workflow/missing/status")

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow 'missing' was not found."


def test_start_workflow_placeholder_file_path() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "string",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "A valid file_path must be provided. Placeholder 'string' is invalid."


def test_start_workflow_empty_file_path() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "   ",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "file_path cannot be empty."


def test_start_workflow_missing_file_path() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "file_path is required."


def test_start_workflow_nonexistent_file() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "nonexistent.txt",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_start_workflow_success() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "sample.txt",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 200
    assert response.json()["workflow_id"] == "WF-API"


def test_start_workflow_cancelled() -> None:
    import pytest
    import asyncio
    import concurrent.futures
    with pytest.raises((asyncio.CancelledError, concurrent.futures.CancelledError)):
        make_client(raise_server_exceptions=True).post(
            "/workflow/start",
            json={
                "workflow_id": "WF-API",
                "file_path": "cancel.txt",
                "confidence_threshold": 0.8,
            },
        )


def test_start_workflow_invalid_api_key() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "invalid_key.txt",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_start_workflow_missing_api_key() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "missing_key.txt",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 401
    assert "missing" in response.json()["detail"].lower()


def test_start_workflow_nested_api_key_error() -> None:
    response = make_client().post(
        "/workflow/start",
        json={
            "workflow_id": "WF-API",
            "file_path": "nested_key.txt",
            "confidence_threshold": 0.8,
        },
    )
    assert response.status_code == 401
    assert "missing" in response.json()["detail"].lower()
