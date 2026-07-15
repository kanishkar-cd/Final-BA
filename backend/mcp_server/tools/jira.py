"""Jira connector — fetches issues and returns only plain text.

Authenticates via ``JIRA_BASE_URL``, ``JIRA_EMAIL``, and ``JIRA_API_TOKEN``
read from the backend ``.env`` file.

Metadata (issue_key, project, reporter, assignee, created, updated, labels)
is persisted to ``storage/metadata/{issue_key}.json`` but is **never**
returned to the caller.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

from mcp_server.utils.metadata_store import save_metadata

logger = logging.getLogger("mcp_server.tools.jira")

# Load .env from the backend root (one level above mcp_server/)
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
class JiraConnector:
    """Connects to Jira Cloud and extracts plain text from issues."""

    def __init__(self) -> None:
        # Explicitly load backend/.env before reading variables
        current_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.abspath(os.path.join(current_dir, "..", "..", ".env"))
        load_dotenv(dotenv_path=env_path, override=True)

        self.base_url = os.getenv("JIRA_BASE_URL", "")
        self.email = os.getenv("JIRA_EMAIL", "")
        self.api_token = os.getenv("JIRA_API_TOKEN", "")

        # Log load status of each variable without revealing the API token value
        logger.info("Jira connector environment configuration:")
        logger.info("- JIRA_BASE_URL loaded: %s", "Yes" if self.base_url else "No")
        logger.info("- JIRA_EMAIL loaded: %s", "Yes" if self.email else "No")
        logger.info("- JIRA_API_TOKEN loaded: %s", "Yes" if self.api_token else "No")

        if not all([self.base_url, self.email, self.api_token]):
            raise ValueError(
                "Jira credentials are incomplete. "
                "Ensure JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN are set in .env"
            )

        from jira import JIRA

        self._client = JIRA(
            server=self.base_url,
            basic_auth=(self.email, self.api_token),
        )
        logger.info("JiraConnector initialised for %s", self.base_url)

    # ── Public API ──────────────────────────────────────────────────────

    def fetch_issue(self, issue_key: str, *, include_comments: bool = False) -> str:
        """Fetch a single Jira issue and return readable plain text.

        Parameters
        ----------
        issue_key:
            The Jira issue key (e.g. ``"KAN-2"``).
        include_comments:
            If ``True``, append comment bodies to the output text.

        Returns
        -------
        str
            Readable plain text only.
        """
        logger.info("Fetching Jira issue: %s", issue_key)
        issue = self._client.issue(issue_key)

        # Build readable text
        parts: list[str] = []

        summary = getattr(issue.fields, "summary", "") or ""
        if summary:
            parts.append(f"Summary: {summary}")

        description = getattr(issue.fields, "description", "") or ""
        if description:
            parts.append(f"\nDescription:\n{description}")

        if include_comments:
            comments = self._client.comments(issue_key)
            if comments:
                parts.append("\nComments:")
                for comment in comments:
                    body = getattr(comment, "body", "") or ""
                    if body:
                        parts.append(f"- {body}")

        raw_text = "\n".join(parts).strip()

        # Store metadata internally
        self._store_metadata(issue, issue_key)

        return raw_text

    def search_issues(
        self,
        jql: str,
        *,
        max_results: int = 50,
        include_comments: bool = False,
    ) -> str:
        """Search issues via JQL and return concatenated plain text.

        Returns
        -------
        str
            All matching issues' text joined with separators.
        """
        logger.info("Searching Jira with JQL: %s (max %d)", jql, max_results)
        issues = self._client.search_issues(jql, maxResults=max_results)

        all_texts: list[str] = []
        for issue in issues:
            key = issue.key
            text = self.fetch_issue(key, include_comments=include_comments)
            all_texts.append(text)

        return "\n\n---\n\n".join(all_texts)

    # ── Metadata (internal only) ────────────────────────────────────────

    def _store_metadata(self, issue: Any, issue_key: str) -> None:
        """Persist issue metadata to storage/metadata/{issue_key}.json."""
        fields = issue.fields

        reporter = ""
        if hasattr(fields, "reporter") and fields.reporter:
            reporter = getattr(fields.reporter, "displayName", str(fields.reporter))

        assignee = ""
        if hasattr(fields, "assignee") and fields.assignee:
            assignee = getattr(fields.assignee, "displayName", str(fields.assignee))

        labels = list(getattr(fields, "labels", []) or [])

        project_key = ""
        if hasattr(fields, "project") and fields.project:
            project_key = getattr(fields.project, "key", str(fields.project))

        metadata = {
            "issue_key": issue_key,
            "project": project_key,
            "reporter": reporter,
            "assignee": assignee,
            "created": str(getattr(fields, "created", "")),
            "updated": str(getattr(fields, "updated", "")),
            "labels": labels,
        }
        save_metadata(issue_key, metadata)
