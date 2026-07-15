"""Confluence connector — fetches pages and returns only plain text.

Authenticates via ``CONFLUENCE_URL``, ``CONFLUENCE_EMAIL``, and
``CONFLUENCE_API_TOKEN`` read from the backend ``.env`` file.

Metadata (page_id, title, space, author, version, created, updated, page_url)
is persisted to ``storage/metadata/{page_id}.json`` but is **never**
returned to the caller.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

from mcp_server.utils.metadata_store import save_metadata
from mcp_server.utils.text_utils import html_to_text

logger = logging.getLogger("mcp_server.tools.confluence")

# Load .env from the backend root (one level above mcp_server/)
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(dotenv_path=_ENV_PATH)


class ConfluenceConnector:
    """Connects to Confluence Cloud and extracts plain text from pages."""

    def __init__(self) -> None:
        self.url = os.getenv("CONFLUENCE_URL", "")
        self.email = os.getenv("CONFLUENCE_EMAIL", "")
        self.api_token = os.getenv("CONFLUENCE_API_TOKEN", "")

        if not all([self.url, self.email, self.api_token]):
            raise ValueError(
                "Confluence credentials are incomplete. "
                "Ensure CONFLUENCE_URL, CONFLUENCE_EMAIL, and "
                "CONFLUENCE_API_TOKEN are set in .env"
            )

        from atlassian import Confluence

        self._client = Confluence(
            url=self.url,
            username=self.email,
            password=self.api_token,
            cloud=True,
        )
        logger.info("ConfluenceConnector initialised for %s", self.url)

    # ── Public API ──────────────────────────────────────────────────────

    def fetch_page(self, page_id: str) -> str:
        """Fetch a Confluence page by ID and return readable plain text.

        Parameters
        ----------
        page_id:
            The numeric Confluence page ID.

        Returns
        -------
        str
            Readable plain text only.
        """
        logger.info("Fetching Confluence page: %s", page_id)

        page = self._client.get_page_by_id(
            page_id,
            expand="body.storage,version,space,history",
        )

        # Extract HTML storage body → plain text
        storage_html = (
            page.get("body", {}).get("storage", {}).get("value", "")
        )
        raw_text = html_to_text(storage_html) if storage_html else ""

        # Store metadata internally
        self._store_metadata(page, page_id)

        return raw_text

    def search_pages(self, query: str, *, max_results: int = 10) -> str:
        """Search Confluence via CQL and return concatenated plain text.

        Parameters
        ----------
        query:
            CQL query string or free-text title search.
        max_results:
            Max pages to retrieve.

        Returns
        -------
        str
            All matching pages' text joined with separators.
        """
        logger.info("Searching Confluence: %s (max %d)", query, max_results)

        # Use CQL search
        cql = query
        if not any(kw in query.lower() for kw in ["=", "~", "and", "or"]):
            # If it doesn't look like CQL, wrap in a title search
            cql = f'title ~ "{query}" OR text ~ "{query}"'

        results = self._client.cql(cql, limit=max_results)
        pages = results.get("results", [])

        all_texts: list[str] = []
        for page_result in pages:
            content = page_result.get("content", page_result)
            pid = str(content.get("id", ""))
            if pid:
                try:
                    text = self.fetch_page(pid)
                    if text:
                        all_texts.append(text)
                except Exception:
                    logger.warning("Failed to fetch page %s during search", pid)

        return "\n\n---\n\n".join(all_texts)

    # ── Metadata (internal only) ────────────────────────────────────────

    def _store_metadata(self, page: dict[str, Any], page_id: str) -> None:
        """Persist page metadata to storage/metadata/{page_id}.json."""
        space = page.get("space", {})
        version_info = page.get("version", {})
        history = page.get("history", {})
        _links = page.get("_links", {})

        author = ""
        created_by = history.get("createdBy", {}) or version_info.get("by", {})
        if created_by:
            author = created_by.get("displayName", created_by.get("username", ""))

        page_url = ""
        base = _links.get("base", self.url.rstrip("/wiki"))
        webui = _links.get("webui", "")
        if webui:
            page_url = f"{base}{webui}"

        metadata = {
            "page_id": page_id,
            "title": page.get("title", ""),
            "space": space.get("key", ""),
            "author": author,
            "version": version_info.get("number", 1),
            "created": str(history.get("createdDate", "")),
            "updated": str(version_info.get("when", "")),
            "page_url": page_url,
        }
        save_metadata(page_id, metadata)
