"""MCP Server — FastAPI router for enterprise data connectors.

Exposes four endpoints (mounted at /mcp/* inside the main backend):

    GET  /mcp/health              — liveness probe
    POST /mcp/fetch               — unified dispatch (jira | confluence)
    POST /mcp/jira/fetch          — fetch one Jira issue by issue key
    POST /mcp/confluence/fetch    — fetch one Confluence page by page ID

Every endpoint returns ONLY { "raw_text": "..." }.
Metadata is stored internally under mcp_server/storage/metadata/ and is
never included in any response.

Google Drive has been removed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from mcp_server.schemas.mcp_schemas import (
    ConfluenceFetchRequest,
    JiraFetchRequest,
    MCPFetchRequest,
    MCPFetchResponse,
)
from mcp_server.services.connector_factory import ConnectorFactory

logger = logging.getLogger("mcp_server.app")

router = APIRouter(prefix="/mcp", tags=["MCP Enterprise Connectors"])


# ── Health ────────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    summary="MCP Server — health check",
    response_description="Liveness probe",
)
async def mcp_health() -> dict[str, str]:
    """Returns ``{"status": "ok"}`` when the MCP module is running."""
    return {"status": "ok", "module": "mcp_server"}


# ── Jira ──────────────────────────────────────────────────────────────────────

@router.post(
    "/jira/fetch",
    response_model=MCPFetchResponse,
    summary="Jira — fetch one issue by key → raw_text → Agent-1",
    description=(
        "Fetches a Jira issue by its key, extracts **summary + description** "
        "(and optionally comments) as plain text, stores metadata internally, "
        "and returns **only** `raw_text`.\n\n"
        "The `raw_text` is forwarded directly to the ingestion layer and then "
        "to **Agent-1 (Requirement Analysis)**.\n\n"
        "**Example request:**\n"
        "```json\n"
        '{"issue_key": "KAN-2", "include_comments": false}\n'
        "```\n\n"
        "**Example response:**\n"
        "```json\n"
        '{"raw_text": "Summary: User login\\n\\nDescription:\\nThe system shall allow users to log in using email and password."}\n'
        "```"
    ),
)
async def jira_fetch(request: JiraFetchRequest) -> MCPFetchResponse:
    try:
        connector = ConnectorFactory.get_connector("jira")
        raw_text = connector.fetch_issue(
            request.issue_key,
            include_comments=request.include_comments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Jira fetch failed for issue=%s", request.issue_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Jira fetch failed: {exc}",
        ) from exc
    return MCPFetchResponse(raw_text=raw_text)


# ── Confluence ────────────────────────────────────────────────────────────────

@router.post(
    "/confluence/fetch",
    response_model=MCPFetchResponse,
    summary="Confluence — fetch one page by ID → raw_text → Agent-1",
    description=(
        "Fetches a Confluence page by its numeric page ID, converts the HTML "
        "storage body to plain text, stores metadata internally, and returns "
        "**only** `raw_text`.\n\n"
        "The `raw_text` is forwarded directly to the ingestion layer and then "
        "to **Agent-1 (Requirement Analysis)**.\n\n"
        "Find your page ID in the Confluence URL:\n"
        "`https://yoursite.atlassian.net/wiki/spaces/SPACE/pages/**<PAGE_ID>**/Title`\n\n"
        "**Example request:**\n"
        "```json\n"
        '{"page_id": "524289"}\n'
        "```\n\n"
        "**Example response:**\n"
        "```json\n"
        '{"raw_text": "The customer shall login using email and password.\\n\\nPassword reset shall be available."}\n'
        "```"
    ),
)
async def confluence_fetch(request: ConfluenceFetchRequest) -> MCPFetchResponse:
    try:
        connector = ConnectorFactory.get_connector("confluence")
        raw_text = connector.fetch_page(request.page_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Confluence fetch failed for page_id=%s", request.page_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confluence fetch failed: {exc}",
        ) from exc
    return MCPFetchResponse(raw_text=raw_text)


# ── Unified dispatch (used by ingestion layer / import_service) ───────────────

@router.post(
    "/fetch",
    response_model=MCPFetchResponse,
    summary="Unified — dispatch to Jira or Confluence → raw_text → Agent-1",
    description=(
        "Single entry-point used by the ingestion layer. "
        "Set `source` to `\"jira\"` or `\"confluence\"` and fill the matching object.\n\n"
        "**Jira example:**\n"
        "```json\n"
        '{"source": "jira", "jira": {"issue_key": "KAN-2", "include_comments": false}}\n'
        "```\n\n"
        "**Confluence example:**\n"
        "```json\n"
        '{"source": "confluence", "confluence": {"page_id": "524289"}}\n'
        "```\n\n"
        "Returns **only** `raw_text` — this value is what Agent-1 receives as input."
    ),
)
async def mcp_fetch(request: MCPFetchRequest) -> MCPFetchResponse:
    try:
        raw_text = _dispatch(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("MCP fetch failed for source=%s", request.source)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MCP fetch failed: {exc}",
        ) from exc
    return MCPFetchResponse(raw_text=raw_text)


# ── Internal helper (called by import_service) ────────────────────────────────

def _dispatch(request: MCPFetchRequest) -> str:
    """Route the request to the correct connector and return raw plain text.

    This function is called directly by ``import_service.import_document()``
    so that the ingestion layer never has to know about individual connectors.
    """
    if request.source == "jira":
        if not request.jira:
            raise ValueError("source='jira' but 'jira' params are missing.")
        connector = ConnectorFactory.get_connector("jira")
        return connector.fetch_issue(
            request.jira.issue_key,
            include_comments=request.jira.include_comments,
        )

    if request.source == "confluence":
        if not request.confluence:
            raise ValueError("source='confluence' but 'confluence' params are missing.")
        connector = ConnectorFactory.get_connector("confluence")
        return connector.fetch_page(request.confluence.page_id)
        
    if request.source == "ado":
        if not request.ado:
            raise ValueError("source='ado' but 'ado' params are missing.")
        from mcp_server.services.azure_service import AzureService
        service = AzureService(
            organization=request.ado.org,
            project=request.ado.project,
            pat_token=request.ado.pat
        )
        wi = service.fetch_work_item(request.ado.work_item_id)
        return wi.formatted_text

    raise ValueError(
        f"Unsupported source: '{request.source}'. Supported: jira, confluence, ado."
    )
