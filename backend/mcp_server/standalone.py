"""MCP Server — standalone FastAPI app for Swagger UI testing.

Start from the backend/ directory:

    pip install -r mcp_server/requirements.txt
    uvicorn mcp_server.standalone:app --reload --port 8001

Then open: http://localhost:8001/docs

You will see four clearly labelled sections:

    Health        GET  /mcp/health
    Jira          POST /mcp/jira/fetch
    Confluence    POST /mcp/confluence/fetch
    Unified       POST /mcp/fetch

Every endpoint returns only {"raw_text": "..."}.
That raw_text is what the ingestion layer passes directly to Agent-1.
"""

from __future__ import annotations

import logging
import os
import sys

# Put backend/ on sys.path so "mcp_server.*" imports resolve correctly
# regardless of which directory uvicorn is launched from.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from fastapi import FastAPI, HTTPException

from mcp_server.schemas.mcp_schemas import (
    ConfluenceFetchRequest,
    JiraFetchRequest,
    MCPFetchRequest,
    MCPFetchResponse,
)
from mcp_server.services.connector_factory import ConnectorFactory
from mcp_server.app import _dispatch

logger = logging.getLogger("mcp_server.standalone")

# ── Tag definitions — these become the visible sections in Swagger UI ─────────
TAGS = [
    {
        "name": "Health",
        "description": "Liveness probe — confirm the MCP server is running.",
    },
    {
        "name": "Jira",
        "description": (
            "Fetch one Jira issue by its **issue key** and receive plain `raw_text`.\n\n"
            "Credentials are read from `backend/.env`:\n"
            "- `JIRA_BASE_URL`\n"
            "- `JIRA_EMAIL`\n"
            "- `JIRA_API_TOKEN`"
        ),
    },
    {
        "name": "Confluence",
        "description": (
            "Fetch one Confluence page by its **page ID** and receive plain `raw_text`.\n\n"
            "Credentials are read from `backend/.env`:\n"
            "- `CONFLUENCE_URL`\n"
            "- `CONFLUENCE_EMAIL`\n"
            "- `CONFLUENCE_API_TOKEN`"
        ),
    },
    {
        "name": "Unified",
        "description": (
            "Single endpoint that dispatches to Jira or Confluence based on `source`. "
            "This is what the ingestion layer calls internally."
        ),
    },
]

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MCP Server — Enterprise Connectors",
    version="1.0.0",
    description=(
        "## MCP Enterprise Connector Layer\n\n"
        "Retrieves plain text from **Jira** and **Confluence**.\n"
        "Returns **only** `raw_text` — no metadata, no IDs, no URLs.\n\n"
        "---\n\n"
        "### Data flow\n"
        "```\n"
        "Swagger UI\n"
        "    │  POST /mcp/jira/fetch   { issue_key: 'KAN-2' }\n"
        "    │  POST /mcp/confluence/fetch  { page_id: '524289' }\n"
        "    ▼\n"
        "MCP Server  ←  reads credentials from backend/.env\n"
        "    │  fetches issue / page\n"
        "    │  stores metadata → mcp_server/storage/metadata/\n"
        "    │  returns raw_text only\n"
        "    ▼\n"
        "Ingestion Layer  (import_service.py)\n"
        "    ▼\n"
        "Agent-1  (RequirementAnalysisAgent)\n"
        "```\n\n"
        "---\n\n"
        "### Start the server\n"
        "```bash\n"
        "# from the backend/ directory\n"
        "pip install -r mcp_server/requirements.txt\n"
        "uvicorn mcp_server.standalone:app --reload --port 8001\n"
        "```\n\n"
        "### Credentials (backend/.env)\n"
        "```\n"
        "JIRA_BASE_URL=https://your-org.atlassian.net\n"
        "JIRA_EMAIL=you@example.com\n"
        "JIRA_API_TOKEN=...\n"
        "CONFLUENCE_URL=https://your-org.atlassian.net/wiki\n"
        "CONFLUENCE_EMAIL=you@example.com\n"
        "CONFLUENCE_API_TOKEN=...\n"
        "```"
    ),
    openapi_tags=TAGS,
)


# ═════════════════════════════════════════════════════════════════════════════
# Health
# ═════════════════════════════════════════════════════════════════════════════

@app.get(
    "/mcp/health",
    tags=["Health"],
    summary="Health check",
    response_description='{"status": "ok", "module": "mcp_server"}',
)
async def health() -> dict:
    """Returns `{"status": "ok"}` when the MCP server is reachable."""
    return {"status": "ok", "module": "mcp_server"}


# ═════════════════════════════════════════════════════════════════════════════
# Jira
# ═════════════════════════════════════════════════════════════════════════════

@app.post(
    "/mcp/jira/fetch",
    tags=["Jira"],
    response_model=MCPFetchResponse,
    summary="Fetch one Jira issue by issue key → raw_text",
    description=(
        "Connects to Jira using credentials from `backend/.env`, fetches the "
        "issue **summary** and **description** (and optionally **comments**), "
        "stores metadata internally, and returns **only** `raw_text`.\n\n"
        "---\n\n"
        "**How to find your issue key:**\n"
        "Open any Jira issue — the key is in the URL and the top-left of the page "
        "(e.g. `KAN-2`, `BA-101`, `SCRUM-7`).\n\n"
        "---\n\n"
        "**Request body:**\n"
        "```json\n"
        "{\n"
        '  "issue_key": "KAN-2",\n'
        '  "include_comments": false\n'
        "}\n"
        "```\n\n"
        "**Response:**\n"
        "```json\n"
        "{\n"
        '  "raw_text": "Summary: User login\\n\\nDescription:\\nThe system shall allow users to log in using email and password."\n'
        "}\n"
        "```\n\n"
        "This `raw_text` is what **Agent-1 (RequirementAnalysisAgent)** receives as input."
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Jira fetch failed for issue=%s", request.issue_key)
        raise HTTPException(status_code=500, detail=f"Jira fetch failed: {exc}") from exc
    return MCPFetchResponse(raw_text=raw_text)


# ═════════════════════════════════════════════════════════════════════════════
# Confluence
# ═════════════════════════════════════════════════════════════════════════════

@app.post(
    "/mcp/confluence/fetch",
    tags=["Confluence"],
    response_model=MCPFetchResponse,
    summary="Fetch one Confluence page by page ID → raw_text",
    description=(
        "Connects to Confluence using credentials from `backend/.env`, fetches "
        "the page body, converts HTML storage format to plain text, "
        "stores metadata internally, and returns **only** `raw_text`.\n\n"
        "---\n\n"
        "**How to find your page ID:**\n"
        "Open the page in Confluence and look at the URL:\n"
        "`https://yoursite.atlassian.net/wiki/spaces/SPACE/pages/**524289**/Page+Title`\n"
        "The number between `/pages/` and the title is your page ID.\n\n"
        "---\n\n"
        "**Request body:**\n"
        "```json\n"
        "{\n"
        '  "page_id": "524289"\n'
        "}\n"
        "```\n\n"
        "**Response:**\n"
        "```json\n"
        "{\n"
        '  "raw_text": "The customer shall login using email and password.\\n\\nPassword reset shall be available."\n'
        "}\n"
        "```\n\n"
        "This `raw_text` is what **Agent-1 (RequirementAnalysisAgent)** receives as input."
    ),
)
async def confluence_fetch(request: ConfluenceFetchRequest) -> MCPFetchResponse:
    try:
        connector = ConnectorFactory.get_connector("confluence")
        raw_text = connector.fetch_page(request.page_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Confluence fetch failed for page_id=%s", request.page_id)
        raise HTTPException(status_code=500, detail=f"Confluence fetch failed: {exc}") from exc
    return MCPFetchResponse(raw_text=raw_text)


# ═════════════════════════════════════════════════════════════════════════════
# Unified
# ═════════════════════════════════════════════════════════════════════════════

@app.post(
    "/mcp/fetch",
    tags=["Unified"],
    response_model=MCPFetchResponse,
    summary="Unified dispatch to Jira or Confluence → raw_text",
    description=(
        "Single endpoint used by the ingestion layer. "
        "Set `source` to `\"jira\"` or `\"confluence\"` and fill the matching object.\n\n"
        "---\n\n"
        "**Jira example:**\n"
        "```json\n"
        "{\n"
        '  "source": "jira",\n'
        '  "jira": {"issue_key": "KAN-2", "include_comments": false}\n'
        "}\n"
        "```\n\n"
        "**Confluence example:**\n"
        "```json\n"
        "{\n"
        '  "source": "confluence",\n'
        '  "confluence": {"page_id": "524289"}\n'
        "}\n"
        "```\n\n"
        "Returns **only** `raw_text` — the value Agent-1 receives."
    ),
)
async def unified_fetch(request: MCPFetchRequest) -> MCPFetchResponse:
    try:
        raw_text = _dispatch(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unified fetch failed for source=%s", request.source)
        raise HTTPException(status_code=500, detail=f"MCP fetch failed: {exc}") from exc
    return MCPFetchResponse(raw_text=raw_text)
