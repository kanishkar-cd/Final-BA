"""Confluence export functionality — push user stories to Confluence pages."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from export.models import (
    ExportRequest,
    ExportResponse,
    ExportStatus,
    StoryExportData,
)

logger = logging.getLogger("export.confluence_export")


class ConfluenceExporter:
    """Exports user stories to Confluence pages."""

    def __init__(self) -> None:
        self.url = os.getenv("CONFLUENCE_URL", "").rstrip("/")
        self.email = os.getenv("CONFLUENCE_EMAIL", "")
        self.api_token = os.getenv("CONFLUENCE_API_TOKEN", "")
        self.space_key = os.getenv("CONFLUENCE_SPACE_KEY", "US")

        # Import and initialize the MCP Confluence connector
        try:
            from mcp_server.tools.confluence import ConfluenceConnector
            self.confluence_client = ConfluenceConnector()._client
            logger.info("ConfluenceExporter initialized using MCP connector")
        except Exception as exc:
            logger.error("Failed to initialize Confluence MCP connector: %s", exc)
            raise ValueError(
                "Could not initialize Confluence MCP connector. "
                "Ensure CONFLUENCE_URL, CONFLUENCE_EMAIL, and CONFLUENCE_API_TOKEN are set in .env"
            ) from exc

    def export(self, request: ExportRequest) -> ExportResponse:
        """Export all user stories into a single Confluence page.

        Parameters
        ----------
        request:
            Export request with stories and metadata.

        Returns
        -------
        ExportResponse
            Export result with created/updated page ID or error.
        """
        export_id = f"confluence_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        logger.info("Starting Confluence export: %s", export_id)

        try:
            # Determine workflow_id from request metadata
            workflow_id = request.metadata.get("workflow_id")
            if not workflow_id:
                workflow_id = datetime.utcnow().strftime('%Y%m%d%H%M%S')

            # Determine Epic name from the first story's epic_mapping
            epic_name = None
            if request.stories:
                first_story = request.stories[0]
                if first_story.epic_mapping and isinstance(first_story.epic_mapping, list) and len(first_story.epic_mapping) > 0:
                    mapping = first_story.epic_mapping[0]
                    if isinstance(mapping, dict):
                        epic_name = mapping.get("name")
            
            # Page Title matching user requirements
            page_title = epic_name if epic_name else f"User Stories - {workflow_id}"

            # Format all stories into a single Confluence Storage Format HTML body
            body_html = self._build_page_content(request.stories)

            # Retrieve optional page_id to update
            page_id = request.metadata.get("page_id")

            if page_id:
                logger.info("Updating existing Confluence page: %s", page_id)
                page_data = self.confluence_client.update_page(
                    page_id=page_id,
                    title=page_title,
                    body=body_html,
                    representation='storage'
                )
            else:
                logger.info("Creating new Confluence page: '%s' in space '%s'", page_title, self.space_key)
                page_data = self.confluence_client.create_page(
                    space=self.space_key,
                    title=page_title,
                    body=body_html,
                    parent_id=None,
                    representation='storage'
                )

            page_id = page_data["id"]
            webui = page_data.get("_links", {}).get("webui", "")
            base = page_data.get("_links", {}).get("base", self.url.rstrip("/wiki"))
            page_url = f"{base}{webui}" if webui else f"{self.url}/spaces/{self.space_key}/pages/{page_id}"

            logger.info("Confluence page export completed. Page ID: %s, URL: %s", page_id, page_url)
            return ExportResponse(
                export_id=export_id,
                status=ExportStatus.COMPLETED,
                format=request.format,
                file_path=page_id,
                download_url=page_url,
                story_count=len(request.stories),
                completed_at=datetime.utcnow(),
                export_metadata={"page_id": page_id, "page_url": page_url}
            )

        except Exception as exc:
            # Do not suppress Confluence API exceptions
            logger.exception("Confluence export failed: %s", exc)
            return ExportResponse(
                export_id=export_id,
                status=ExportStatus.FAILED,
                format=request.format,
                error_message=str(exc),
                story_count=len(request.stories),
            )

    def _build_page_content(self, stories: list[StoryExportData]) -> str:
        """Build Confluence page content in storage format (HTML) for all stories."""
        content_parts = []
        
        # Include TOC at the beginning
        content_parts.append('<p><ac:structured-macro ac:name="toc" /></p>')
        
        for idx, story in enumerate(stories, start=1):
            content_parts.append(f"<h2>{idx}. {story.title} ({story.story_id})</h2>")
            
            if story.user_story:
                content_parts.append(f"<p><strong>User Story:</strong> {story.user_story}</p>")
                
            content_parts.append(f"<p><strong>Description:</strong> {story.description}</p>")
            
            if story.feature:
                content_parts.append(f"<p><strong>Feature Name:</strong> {story.feature}</p>")
                
            # Acceptance Criteria
            content_parts.append("<h3>Acceptance Criteria</h3>")
            if story.acceptance_criteria:
                content_parts.append("<ol>")
                for ac in story.acceptance_criteria:
                    if isinstance(ac, dict) and "description" in ac:
                        content_parts.append(f"<li>{ac['description']}</li>")
                    else:
                        content_parts.append(f"<li>{ac}</li>")
                content_parts.append("</ol>")
            else:
                content_parts.append("<p><em>No acceptance criteria defined.</em></p>")
                
            # Business Rules
            content_parts.append("<h3>Business Rules</h3>")
            if story.business_rules:
                content_parts.append("<ul>")
                for rule in story.business_rules:
                    content_parts.append(f"<li>{rule}</li>")
                content_parts.append("</ul>")
            else:
                content_parts.append("<p><em>No business rules defined.</em></p>")
                
            # Dependencies
            content_parts.append("<h3>Dependencies</h3>")
            if story.dependencies:
                content_parts.append("<ul>")
                for dep in story.dependencies:
                    if isinstance(dep, dict):
                        dep_id = dep.get("id", "N/A")
                        dep_desc = dep.get("description", "")
                        dep_type = dep.get("type", "unknown")
                        content_parts.append(f"<li>{dep_id} ({dep_type}): {dep_desc}</li>")
                    else:
                        content_parts.append(f"<li>{dep}</li>")
                content_parts.append("</ul>")
            else:
                content_parts.append("<p><em>No dependencies.</em></p>")
                
            # Definition of Done
            content_parts.append("<h3>Definition of Done</h3>")
            if story.definition_of_done:
                content_parts.append("<ul>")
                for item in story.definition_of_done:
                    content_parts.append(f"<li>{item}</li>")
                content_parts.append("</ul>")
            else:
                content_parts.append("<p><em>No Definition of Done defined.</em></p>")
                
            # Metadata Table (Priority, Story Points, Confidence Score)
            content_parts.append("<h3>Story Metadata</h3>")
            content_parts.append("<table>")
            content_parts.append("<thead>")
            content_parts.append("<tr>")
            content_parts.append("<th>Priority</th>")
            content_parts.append("<th>Story Points</th>")
            content_parts.append("<th>Confidence Score</th>")
            content_parts.append("</tr>")
            content_parts.append("</thead>")
            content_parts.append("<tbody>")
            content_parts.append("<tr>")
            
            priority_val = story.priority or "Not Set"
            points_val = str(story.story_points) if story.story_points is not None else "Not Set"
            
            confidence = story.metadata.get("confidence_score")
            if isinstance(confidence, (int, float)):
                confidence_str = f"{confidence:.2%}" if confidence <= 1.0 else f"{confidence}%"
            else:
                confidence_str = str(confidence) if confidence else "N/A"
                
            content_parts.append(f"<td>{priority_val}</td>")
            content_parts.append(f"<td>{points_val}</td>")
            content_parts.append(f"<td>{confidence_str}</td>")
            content_parts.append("</tr>")
            content_parts.append("</tbody>")
            content_parts.append("</table>")
            
            content_parts.append("<hr />")
            
        return "\n".join(content_parts)
