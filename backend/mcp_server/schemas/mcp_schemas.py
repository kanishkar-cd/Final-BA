"""Pydantic request / response models for the MCP Server.

Only Jira (by issue key) and Confluence (by page ID) are supported.
Google Drive has been removed.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Jira ─────────────────────────────────────────────────────────────────────

class JiraFetchRequest(BaseModel):
    """Fetch a single Jira issue by its issue key."""

    issue_key: str = Field(
        ...,
        description="Jira issue key (e.g. KAN-2)",
        examples=["KAN-2"],
    )
    include_comments: bool = Field(
        False,
        description="Set to true to include comment bodies in the output",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"issue_key": "KAN-2", "include_comments": False}
        }
    }


# ── Confluence ────────────────────────────────────────────────────────────────

class ConfluenceFetchRequest(BaseModel):
    """Fetch a single Confluence page by its numeric page ID."""

    page_id: str = Field(
        ...,
        description=(
            "Confluence page ID — the number in the page URL: "
            "https://yoursite.atlassian.net/wiki/spaces/SPACE/pages/<PAGE_ID>/Title"
        ),
        examples=["524289"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {"page_id": "524289"}
        }
    }


# ── Unified MCP Request / Response ───────────────────────────────────────────

class MCPFetchRequest(BaseModel):
    """Unified request body for the /mcp/fetch endpoint.

    Set ``source`` to ``"jira"`` or ``"confluence"`` and fill in the
    matching nested object.
    """

    source: Literal["jira", "confluence"] = Field(
        ...,
        description="Which connector to invoke: 'jira' or 'confluence'",
    )
    jira: Optional[JiraFetchRequest] = Field(
        None,
        description="Required when source='jira'",
    )
    confluence: Optional[ConfluenceFetchRequest] = Field(
        None,
        description="Required when source='confluence'",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Fetch a Jira issue",
                    "value": {
                        "source": "jira",
                        "jira": {"issue_key": "KAN-2", "include_comments": False},
                    },
                },
                {
                    "summary": "Fetch a Confluence page",
                    "value": {
                        "source": "confluence",
                        "confluence": {"page_id": "524289"},
                    },
                },
            ]
        }
    }


class MCPFetchResponse(BaseModel):
    """Standard MCP response — only plain text, never metadata."""

    raw_text: str = Field(
        ...,
        description=(
            "Extracted plain text from the source. "
            "This is the only value forwarded to the ingestion layer and Agent-1."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "raw_text": (
                    "Summary: User login with email and password\n\n"
                    "Description:\nThe system shall allow users to log in using "
                    "their registered email address and password.\n"
                    "Password reset shall be available via email verification."
                )
            }
        }
    }
