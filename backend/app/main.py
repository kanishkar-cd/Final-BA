from __future__ import annotations

import os
from pathlib import Path

# Load .env before any os.getenv() calls are made
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

# BA Accelerator Backend — entry point
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.router import api_router
from app.database.connection import engine
from app.database.migrations import ensure_database_schema
from app.schemas.user_story import ApiResponse
from app.services.preprocessing_pipeline_service import PreprocessingPipelineError
from app.utils import shutdown
from app.shared.llm_client import LLMServiceAuthenticationError, LLMServiceConfigurationError

app = FastAPI(
    title="BA Accelerator Backend",
    version="0.1.0",
    description=(
        "Pipeline-based backend for requirement, planning, and user story workflows.\n\n"
        "Includes MCP enterprise connectors for **Jira** and **Confluence**.\n\n"
        "### MCP quick-test endpoints\n"
        "| Source | Endpoint | Input |\n"
        "|--------|----------|-------|\n"
        "| Jira | `POST /api/mcp/jira/fetch` | `{\"issue_key\": \"KAN-2\"}` |\n"
        "| Confluence | `POST /api/mcp/confluence/fetch` | `{\"page_id\": \"524289\"}` |\n\n"
        "### Full pipeline (MCP → Agent-1)\n"
        "| Source | Endpoint | Input |\n"
        "|--------|----------|-------|\n"
        "| Jira | `POST /api/workflow/mcp/jira/start` | `{\"issue_key\": \"KAN-2\"}` |\n"
        "| Confluence | `POST /api/workflow/mcp/confluence/start` | `{\"page_id\": \"524289\"}` |\n"
    ),
    openapi_tags=[
        {
            "name": "MCP Enterprise Connectors",
            "description": (
                "Enterprise data connectors — **Jira** and **Confluence**. "
                "Every endpoint returns only `raw_text`. "
                "Endpoints are available at `/api/mcp/*`."
            ),
        },
        {
            "name": "Workflow",
            "description": (
                "Start and inspect LangGraph workflows. "
                "Use `/api/workflow/mcp/jira/start` or `/api/workflow/mcp/confluence/start` "
                "to run the full MCP → raw_text → Agent-1 pipeline."
            ),
        },
    ],
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
async def initialize_database_schema() -> None:
    """Ensure a newly configured PostgreSQL database is ready before requests."""
    await ensure_database_schema(engine)


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    """Redirect bare root URL to Swagger UI."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(HTTPException)
async def http_exception_handler(
    _request: Request,
    exc: HTTPException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            success=False,
            message=str(exc.detail),
            errors=[str(exc.detail)],
        ).model_dump(),
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_exception_handler(
    _request: Request,
    exc: FileNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ApiResponse(
            success=False,
            message=str(exc),
            errors=[str(exc)],
        ).model_dump(),
    )


def find_cause(exc: BaseException | None, target_types: tuple[type[BaseException], ...]) -> BaseException | None:
    current = exc
    while current is not None:
        if isinstance(current, target_types):
            return current
        current = current.__cause__ or current.__context__
    return None


@app.exception_handler(PreprocessingPipelineError)
async def preprocessing_pipeline_exception_handler(
    _request: Request,
    exc: PreprocessingPipelineError,
) -> JSONResponse:
    error_msg = str(exc)
    
    # Check if the underlying cause was an authentication or missing API key error
    auth_cause = find_cause(exc, (LLMServiceAuthenticationError, LLMServiceConfigurationError))
    if auth_cause is not None or "unauthorized" in error_msg.lower() or "api key is missing" in error_msg.lower():
        msg = str(auth_cause) if auth_cause else error_msg
        return JSONResponse(
            status_code=401,
            content=ApiResponse(
                success=False,
                message=msg,
                errors=[msg],
            ).model_dump(),
        )

    is_not_found = (
        "not found" in error_msg.lower()
        or (exc.__cause__ and "not found" in str(exc.__cause__).lower())
        or isinstance(exc.__cause__, FileNotFoundError)
    )
    if is_not_found:
        return JSONResponse(
            status_code=404,
            content=ApiResponse(
                success=False,
                message=error_msg,
                errors=[error_msg],
            ).model_dump(),
        )
    return JSONResponse(
        status_code=500,
        content=ApiResponse(
            success=False,
            message="Internal pipeline processing failure.",
            errors=[error_msg],
        ).model_dump(),
    )


@app.exception_handler(LLMServiceAuthenticationError)
async def llm_service_auth_exception_handler(
    _request: Request,
    exc: LLMServiceAuthenticationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=ApiResponse(
            success=False,
            message=str(exc),
            errors=[str(exc)],
        ).model_dump(),
    )


@app.exception_handler(LLMServiceConfigurationError)
async def llm_service_config_exception_handler(
    _request: Request,
    exc: LLMServiceConfigurationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=ApiResponse(
            success=False,
            message=str(exc),
            errors=[str(exc)],
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    # Check if the unhandled exception was caused by a deep LLM auth/config failure
    auth_cause = find_cause(exc, (LLMServiceAuthenticationError, LLMServiceConfigurationError))
    if auth_cause is not None:
        msg = str(auth_cause)
        return JSONResponse(
            status_code=401,
            content=ApiResponse(
                success=False,
                message=msg,
                errors=[msg],
            ).model_dump(),
        )

    return JSONResponse(
        status_code=500,
        content=ApiResponse(
            success=False,
            message="Unexpected backend error.",
            errors=[str(exc)],
        ).model_dump(),
    )


@app.on_event("shutdown")
def shutdown_event():
    shutdown.set_shutting_down(True)
