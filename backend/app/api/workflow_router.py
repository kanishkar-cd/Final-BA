from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from uuid import uuid4

from app.api.deps import get_workflow_api_service
from app.schemas.workflow import (
    WorkflowStartRequest,
    WorkflowStateResponse,
    WorkflowStatusResponse,
)
from app.services.workflow_service import WorkflowApiService, WorkflowStateNotFoundError


router = APIRouter(prefix="/workflow", tags=["Workflow"])


class EpicRegenerationRequest(BaseModel):
    feedback: str = Field(default="", max_length=2000)


# ── Standard workflow endpoints ───────────────────────────────────────────────

@router.post("/start", response_model=WorkflowStateResponse)
async def start_workflow(
    request: WorkflowStartRequest,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStateResponse:
    if request.file_path is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_path is required.",
        )
    file_path_str = str(request.file_path).strip()
    if not file_path_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_path cannot be empty.",
        )
    if file_path_str.lower() in {"string", "undefined", "null"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A valid file_path must be provided. Placeholder '{file_path_str}' is invalid.",
        )
    return await workflow_service.start(request)


@router.get("/{workflow_id}", response_model=WorkflowStateResponse)
async def get_workflow(
    workflow_id: str,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStateResponse:
    try:
        return await workflow_service.get(workflow_id)
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch("/{workflow_id}")
async def patch_workflow(
    workflow_id: str,
    updates: dict,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> dict:
    try:
        return await workflow_service.update_state_partial(workflow_id, updates)
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/{workflow_id}/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    workflow_id: str,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStatusResponse:
    try:
        return await workflow_service.status(workflow_id)
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/{workflow_id}/epics/{epic_id}/regenerate")
async def regenerate_epic(
    workflow_id: str,
    epic_id: str,
    request: EpicRegenerationRequest,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> dict:
    """Regenerate only the selected epic and preserve the remaining plan."""
    try:
        return await workflow_service.regenerate_epic(
            workflow_id,
            epic_id,
            request.feedback,
        )
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc


class UndoRequest(BaseModel):
    entity_type: str
    entity_id: str
    target_version: int

@router.post("/{workflow_id}/undo")
async def undo_artifact(
    workflow_id: str,
    request: UndoRequest,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> dict:
    """Undo an artifact to a previous version."""
    try:
        return await workflow_service.undo_artifact(
            workflow_id,
            request.entity_type,
            request.entity_id,
            request.target_version,
        )
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc

@router.post("/{workflow_id}/approve-outline")
async def approve_outline(
    workflow_id: str,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> dict:
    """Approve the epic/feature outline and transition the workflow status."""
    try:
        return await workflow_service.update_state_partial(workflow_id, {"workflow_status": "OUTLINE_APPROVED"})
    except WorkflowStateNotFoundError as exc:
        raise _not_found(exc) from exc

# ── MCP → Agent-1 workflow endpoints ─────────────────────────────────────────
# These endpoints let you start the full pipeline directly from a Jira issue
# key or a Confluence page ID.  The MCP connector fetches raw_text, which is
# passed through the ingestion layer straight into Agent-1.

class JiraWorkflowRequest(BaseModel):
    """Start the requirement analysis pipeline from a Jira issue."""

    issue_key: str = Field(
        ...,
        description="Jira issue key (e.g. KAN-2). The MCP connector will fetch the issue text.",
        examples=["KAN-2"],
    )
    include_comments: bool = Field(
        False,
        description="Include Jira comment bodies in the text sent to Agent-1.",
    )
    workflow_id: str = Field(
        default_factory=lambda: f"WF-{uuid4().hex[:8].upper()}",
        description="Optional workflow ID. Auto-generated if not provided.",
    )
    project_id: str | None = Field(None, description="Optional project ID for traceability.")
    confidence_threshold: float = Field(0.8, ge=0, le=1)
    max_retry_attempts: int = Field(3, ge=0, le=5)

    model_config = {
        "json_schema_extra": {
            "example": {
                "issue_key": "KAN-2",
                "include_comments": False,
                "workflow_id": "WF-AUTO",
                "project_id": None,
                "confidence_threshold": 0.8,
                "max_retry_attempts": 3,
            }
        }
    }


class ConfluenceWorkflowRequest(BaseModel):
    """Start the requirement analysis pipeline from a Confluence page."""

    page_id: str = Field(
        ...,
        description=(
            "Confluence page ID — the number in the page URL: "
            "https://yoursite.atlassian.net/wiki/spaces/SPACE/pages/<PAGE_ID>/Title"
        ),
        examples=["524289"],
    )
    workflow_id: str = Field(
        default_factory=lambda: f"WF-{uuid4().hex[:8].upper()}",
        description="Optional workflow ID. Auto-generated if not provided.",
    )
    project_id: str | None = Field(None, description="Optional project ID for traceability.")
    confidence_threshold: float = Field(0.8, ge=0, le=1)
    max_retry_attempts: int = Field(3, ge=0, le=5)

    model_config = {
        "json_schema_extra": {
            "example": {
                "page_id": "524289",
                "workflow_id": "WF-AUTO",
                "project_id": None,
                "confidence_threshold": 0.8,
                "max_retry_attempts": 3,
            }
        }
    }


class AdoWorkflowRequest(BaseModel):
    """Start the requirement analysis pipeline from an Azure DevOps Work Item."""
    org: str
    project: str
    pat: str
    work_item_id: str
    workflow_id: str = Field(
        default_factory=lambda: f"WF-{uuid4().hex[:8].upper()}",
    )
    project_id: str | None = Field(None)
    confidence_threshold: float = Field(0.8, ge=0, le=1)
    max_retry_attempts: int = Field(3, ge=0, le=5)

@router.post(
    "/mcp/ado/start",
    response_model=WorkflowStateResponse,
    summary="ADO → MCP → raw_text → Agent-1 — start full pipeline",
    tags=["Workflow"],
)
async def start_workflow_from_ado(
    request: AdoWorkflowRequest,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStateResponse:
    """Kick off the full pipeline using an ADO Work Item as the document source."""
    mcp_source = f"ado:{request.org}:{request.project}:{request.pat}:{request.work_item_id}"

    workflow_request = WorkflowStartRequest(
        workflow_id=request.workflow_id,
        file_path=mcp_source,
        project_id=request.project_id,
        confidence_threshold=request.confidence_threshold,
        max_retry_attempts=request.max_retry_attempts,
        metadata={"mcp_source": "ado", "work_item_id": request.work_item_id},
    )
    return await workflow_service.start(workflow_request)

@router.post(
    "/mcp/jira/start",
    response_model=WorkflowStateResponse,
    summary="Jira → MCP → raw_text → Agent-1 — start full pipeline",
    description=(
        "Fetches the Jira issue via the MCP connector, extracts plain `raw_text`, "
        "and starts the full requirement analysis pipeline through **Agent-1**.\n\n"
        "**Flow:**\n"
        "```\n"
        "POST /workflow/mcp/jira/start  { issue_key: 'KAN-2' }\n"
        "        │\n"
        "        ▼\n"
        "MCP Connector  →  Jira API  →  fetches issue text\n"
        "        │  stores metadata internally (never forwarded)\n"
        "        │  returns raw_text only\n"
        "        ▼\n"
        "Ingestion Layer  (import_service)\n"
        "        ▼\n"
        "Semantic Chunker\n"
        "        ▼\n"
        "Context Labeler\n"
        "        ▼\n"
        "Agent-1  (RequirementAnalysisAgent)\n"
        "        │  extracts actors, functional/non-functional requirements,\n"
        "        │  dependencies, business goals, edge cases, constraints\n"
        "        ▼\n"
        "WorkflowStateResponse\n"
        "```\n\n"
        "**Example request:**\n"
        "```json\n"
        '{"issue_key": "KAN-2", "include_comments": false}\n'
        "```"
    ),
    tags=["Workflow"],
)
async def start_workflow_from_jira(
    request: JiraWorkflowRequest,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStateResponse:
    """Kick off the full pipeline using a Jira issue as the document source."""
    # Build the MCP source identifier that import_service understands
    mcp_source = f"jira:{request.issue_key}"
    if request.include_comments:
        mcp_source += ",comments"

    workflow_request = WorkflowStartRequest(
        workflow_id=request.workflow_id,
        file_path=mcp_source,
        project_id=request.project_id,
        confidence_threshold=request.confidence_threshold,
        max_retry_attempts=request.max_retry_attempts,
        metadata={"mcp_source": "jira", "issue_key": request.issue_key},
    )
    return await workflow_service.start(workflow_request)


@router.post(
    "/mcp/confluence/start",
    response_model=WorkflowStateResponse,
    summary="Confluence → MCP → raw_text → Agent-1 — start full pipeline",
    description=(
        "Fetches the Confluence page via the MCP connector, extracts plain `raw_text`, "
        "and starts the full requirement analysis pipeline through **Agent-1**.\n\n"
        "**Flow:**\n"
        "```\n"
        "POST /workflow/mcp/confluence/start  { page_id: '524289' }\n"
        "        │\n"
        "        ▼\n"
        "MCP Connector  →  Confluence API  →  fetches page HTML → plain text\n"
        "        │  stores metadata internally (never forwarded)\n"
        "        │  returns raw_text only\n"
        "        ▼\n"
        "Ingestion Layer  (import_service)\n"
        "        ▼\n"
        "Semantic Chunker\n"
        "        ▼\n"
        "Context Labeler\n"
        "        ▼\n"
        "Agent-1  (RequirementAnalysisAgent)\n"
        "        │  extracts actors, functional/non-functional requirements,\n"
        "        │  dependencies, business goals, edge cases, constraints\n"
        "        ▼\n"
        "WorkflowStateResponse\n"
        "```\n\n"
        "**Example request:**\n"
        "```json\n"
        '{"page_id": "524289"}\n'
        "```"
    ),
    tags=["Workflow"],
)
async def start_workflow_from_confluence(
    request: ConfluenceWorkflowRequest,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStateResponse:
    """Kick off the full pipeline using a Confluence page as the document source."""
    workflow_request = WorkflowStartRequest(
        workflow_id=request.workflow_id,
        file_path=f"confluence:{request.page_id}",
        project_id=request.project_id,
        confidence_threshold=request.confidence_threshold,
        max_retry_attempts=request.max_retry_attempts,
        metadata={"mcp_source": "confluence", "page_id": request.page_id},
    )
    return await workflow_service.start(workflow_request)


class SharePointWorkflowRequest(BaseModel):
    site_url: str
    folder_path: str | None = None
    document_library: str | None = None
    file_name: str | None = None
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    confidence_threshold: float = Field(default=0.8)
    max_retry_attempts: int = Field(default=3)
    project_id: str | None = Field(default=None)
    workflow_id: str | None = Field(default=None)
    validation_mode: str | None = Field(default="every-step")


@router.post(
    "/mcp/sharepoint/start",
    response_model=WorkflowStateResponse,
    summary="SharePoint → MCP → raw_text → Agent-1 — start full pipeline",
    tags=["Workflow"],
)
async def start_workflow_from_sharepoint(
    request: SharePointWorkflowRequest,
    workflow_service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStateResponse:
    """Kick off the full pipeline using a SharePoint site, document library, folder, and file."""
    parts = []
    if request.document_library:
        parts.append(request.document_library.strip("/"))
    if request.folder_path:
        parts.append(request.folder_path.strip("/"))
    if request.file_name:
        parts.append(request.file_name.strip("/"))
    
    full_path = "/".join(parts) if parts else (request.folder_path or "")

    sp_source = f"sharepoint:{request.site_url}|{full_path}"
    workflow_request = WorkflowStartRequest(
        workflow_id=request.workflow_id,
        file_path=sp_source,
        project_id=request.project_id,
        confidence_threshold=request.confidence_threshold,
        max_retry_attempts=request.max_retry_attempts,
        metadata={
            "mcp_source": "sharepoint",
            "site_url": request.site_url,
            "folder_path": full_path,
            "document_library": request.document_library,
            "file_name": request.file_name,
        },
    )
    return await workflow_service.start(workflow_request)


# ── Helper ────────────────────────────────────────────────────────────────────

def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
