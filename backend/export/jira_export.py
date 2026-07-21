"""Jira export functionality — creates Epics and Stories using the MCP connector.

This module uses the existing JiraConnector from mcp_server.tools.jira
(no duplicate authentication). It creates:
1. One Epic per unique story.epic_mapping[0].name
2. One Story per user story, linked to the Epic as parent
3. Issue links for traceability if export_metadata.original_issue_key exists

All issue keys are generated automatically by Jira.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import os

from export.models import (
    ExportRequest,
    ExportResponse,
    ExportStatus,
    StoryExportData,
)

logger = logging.getLogger("export.jira_export")


class JiraExporter:
    """Exports user stories to Jira using the MCP connector.
    
    Creates a hierarchy:
    - Epic (from epic_mapping or epic metadata)
      └─ Story (from each user story, linked as child)
    """

    def __init__(self) -> None:
        # Load configuration directly from environment variables
        self.project_key = os.getenv("JIRA_PROJECT_KEY") or os.getenv("PROJECT_KEY") or os.getenv("JIRA_PROJECT") or "KAN"
        self.issue_type = os.getenv("JIRA_ISSUE_TYPE", "Story")
        self.assign_to_me = os.getenv("JIRA_ASSIGN_TO_ME", "false").lower() == "true"
        self.email = os.getenv("JIRA_EMAIL")
        
        # Import and initialize the MCP Jira connector
        try:
            from mcp_server.tools.jira import JiraConnector
            self.jira_client = JiraConnector()._client  # Access underlying JIRA client
            logger.info("JiraExporter initialized using MCP connector")
        except Exception as exc:
            logger.error("Failed to initialize Jira MCP connector: %s", exc)
            raise ValueError(
                "Could not initialize Jira MCP connector. "
                "Ensure JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN are set in .env"
            ) from exc

        # Determine if the project is team-managed
        try:
            project = self.jira_client.project(self.project_key)
            self.is_team_managed = getattr(project, "style", "") == "next-gen"
            logger.info("Project %s is team-managed (next-gen): %s", self.project_key, self.is_team_managed)
        except Exception as exc:
            logger.warning("Could not determine project style for %s, defaulting to classic (company-managed): %s", self.project_key, exc)
            self.is_team_managed = False

        # Validate supported fields and dynamically discover the Story Points field
        self.story_points_field = None
        try:
            fields = self.jira_client.fields()
            self.supported_fields = {f["id"] for f in fields}
            
            # Search for Story Points / Story Point Estimate custom field
            for f in fields:
                field_name = f.get("name", "").lower()
                if field_name in ("story points", "story point estimate"):
                    self.story_points_field = f["id"]
                    logger.info("Discovered Story Points field: %s (%s)", self.story_points_field, f.get("name"))
                    break
                    
            logger.info("Jira project %s has %d supported fields", self.project_key, len(self.supported_fields))
        except Exception as exc:
            logger.warning("Could not fetch fields configuration from Jira, defaulting to empty: %s", exc)
            self.supported_fields = set()

    def export(self, request: ExportRequest) -> ExportResponse:
        """Export user stories to Jira as Epics + Stories.

        Parameters
        ----------
        request:
            Export request with stories and export metadata.

        Returns
        -------
        ExportResponse
            Export result with created issue keys or error.
        """
        export_id = f"jira_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        logger.info("Starting Jira export: %s", export_id)

        try:
            created_epics = {}  # Map epic_name -> epic_key
            created_stories = []
            failed_stories = []
            created_links = []

            # Determine the original issue key (for linking) from metadata or request
            original_issue_key = (
                request.metadata.get("original_issue_key")
                or request.metadata.get("export_metadata", {}).get("original_issue_key")
            )

            for story in request.stories:
                # 1. Determine the Epic Name
                epic_name = None
                if story.epic_mapping and isinstance(story.epic_mapping, list) and len(story.epic_mapping) > 0:
                    mapping = story.epic_mapping[0]
                    if isinstance(mapping, dict):
                        epic_name = mapping.get("name")
                
                # Fallback to story.epic if mapping was empty or invalid
                if not epic_name:
                    epic_name = story.epic or request.project_name or "General Epic"

                # 2. Create the Epic if not already created
                if epic_name not in created_epics:
                    try:
                        logger.info("Creating Epic: %s", epic_name)
                        epic_key = self._create_epic(epic_name, story.description)
                        created_epics[epic_name] = epic_key
                        logger.info("Created Epic %s for %s", epic_key, epic_name)
                    except Exception as exc:
                        logger.exception("Failed to create Epic for %s: %s", epic_name, exc)
                        raise exc

                target_epic_key = created_epics[epic_name]

                # 3. Create the User Story
                try:
                    story_key = self._create_story(story, target_epic_key)
                    created_stories.append(story_key)
                    logger.info("Created Story: %s for %s", story_key, story.story_id)

                    # 4. Handle linking if original_issue_key is specified
                    # Fallback to story-level metadata if request metadata didn't have it
                    story_original_key = original_issue_key or story.metadata.get("original_issue_key")
                    if story_original_key:
                        link_type = self._create_issue_link(story_key, story_original_key)
                        if link_type:
                            created_links.append({
                                "story_key": story_key,
                                "original_issue_key": story_original_key,
                                "link_type": link_type
                            })
                except Exception as exc:
                    logger.exception("Failed to create Story for %s: %s", story.story_id, exc)
                    raise exc

            # Build response metadata
            export_metadata_res = {
                "epic_keys": list(filter(None, created_epics.values())),
                "story_keys": created_stories,
                "issue_links": created_links,
            }

            # For backwards compatibility with outputs that expect a single key
            first_epic_key = next((k for k in created_epics.values() if k), None)

            if failed_stories:
                error_msg = f"Completed with failed stories: {', '.join(failed_stories)}"
                logger.warning(error_msg)
                status = ExportStatus.FAILED if len(failed_stories) == len(request.stories) else ExportStatus.COMPLETED
            else:
                error_msg = None
                status = ExportStatus.COMPLETED

            download_url = None
            if first_epic_key:
                server_url = self.jira_client._options.get('server', '').rstrip('/')
                if server_url:
                    download_url = f"{server_url}/browse/{first_epic_key}"

            logger.info("Jira export completed: %d Epics, %d Stories", len(export_metadata_res["epic_keys"]), len(created_stories))
            return ExportResponse(
                export_id=export_id,
                status=status,
                format=request.format,
                file_path=first_epic_key,
                download_url=download_url,
                error_message=error_msg,
                story_count=len(created_stories),
                completed_at=datetime.utcnow(),
                export_metadata=export_metadata_res,
            )

        except Exception as exc:
            from jira import JIRAError
            error_message = str(exc)
            if isinstance(exc, JIRAError) and hasattr(exc, "text") and exc.text:
                error_message = f"Jira API Error: {exc.text}"
            logger.exception("Jira export failed: %s", error_message)
            return ExportResponse(
                export_id=export_id,
                status=ExportStatus.FAILED,
                format=request.format,
                error_message=error_message,
                story_count=0,
            )

    def _create_epic(self, summary: str, description: str) -> str:
        """Create a Jira Epic.

        Parameters
        ----------
        summary:
            Epic summary.
        description:
            Epic description.

        Returns
        -------
        str
            Created Epic key (e.g., "PROJ-123").
        """
        issue_dict = {
            "project": {"key": self.project_key},
            "summary": summary,
            "description": description or f"Epic for {summary}",
            "issuetype": {"name": "Epic"},
        }

        # Validate Epic custom field customfield_10011 before using it
        if "customfield_10011" in self.supported_fields:
            issue_dict["customfield_10011"] = summary

        new_issue = self.jira_client.create_issue(fields=issue_dict)
        return new_issue.key

    def _format_description(self, story: StoryExportData) -> str:
        """Format story fields into a comprehensive markdown description for Jira."""
        parts = []
        
        parts.append(f"*Story Title:* {story.title}")
        parts.append(f"\n*Description:*\n{story.description}")
        
        if story.acceptance_criteria:
            parts.append("\n*Acceptance Criteria:*")
            for idx, ac in enumerate(story.acceptance_criteria, start=1):
                if isinstance(ac, dict) and "description" in ac:
                    parts.append(f"{idx}. {ac['description']}")
                else:
                    parts.append(f"{idx}. {ac}")
                    
        if story.business_rules:
            parts.append("\n*Business Rules:*")
            for br in story.business_rules:
                parts.append(f"* {br}")
                
        if story.dependencies:
            parts.append("\n*Dependencies:*")
            for dep in story.dependencies:
                if isinstance(dep, dict):
                    dep_id = dep.get("id", "N/A")
                    dep_desc = dep.get("description", "")
                    dep_type = dep.get("type", "unknown")
                    parts.append(f"* {dep_id} ({dep_type}): {dep_desc}")
                else:
                    parts.append(f"* {dep}")
                    
        if story.definition_of_done:
            parts.append("\n*Definition of Done:*")
            for item in story.definition_of_done:
                parts.append(f"* ✓ {item}")
                
        parts.append(f"\n*Priority:* {story.priority or 'Not Set'}")
        parts.append(f"*Story Points:* {story.story_points if story.story_points is not None else 'Not Set'}")
        
        return "\n".join(parts)

    def _create_story(self, story: StoryExportData, epic_key: str | None) -> str:
        """Create a Jira Story linked to an Epic.

        Parameters
        ----------
        story:
            User story data.
        epic_key:
            Parent Epic key.

        Returns
        -------
        str
            Created Story key (e.g., "PROJ-124").
        """
        # Format the description using required fields
        description = self._format_description(story)

        # Build issue dict
        issue_dict = {
            "project": {"key": self.project_key},
            "summary": story.user_story or story.title,
            "description": description,
            "issuetype": {"name": self.issue_type},
        }

        # Link to Epic (parent field)
        if epic_key:
            if self.is_team_managed:
                issue_dict["parent"] = {"key": epic_key}
            else:
                issue_dict["customfield_10014"] = epic_key

        # Set priority
        if story.priority:
            try:
                issue_dict["priority"] = {"name": story.priority}
            except Exception:
                logger.warning("Could not set priority %s for story %s", story.priority, story.story_id)

        # Set story points dynamically if the field exists
        if story.story_points is not None and self.story_points_field:
            try:
                issue_dict[self.story_points_field] = story.story_points
            except Exception:
                logger.warning("Could not set story points for story %s using field %s", story.story_id, self.story_points_field)

        # Set labels
        if story.labels:
            issue_dict["labels"] = story.labels

        # Set assignee if configured
        if self.assign_to_me:
            try:
                issue_dict["assignee"] = {"emailAddress": self.email}
            except Exception:
                logger.warning("Could not assign story %s", story.story_id)

        # Create the issue with retry logic for common field errors
        try:
            new_issue = self.jira_client.create_issue(fields=issue_dict)
            return new_issue.key
        except Exception as exc:
            from jira import JIRAError
            if isinstance(exc, JIRAError) and hasattr(exc, "response") and exc.response is not None:
                try:
                    error_data = exc.response.json()
                    errors = error_data.get("errors", {})
                    
                    retry = False
                    if "priority" in errors:
                        logger.warning("Priority '%s' is invalid. Retrying without priority.", story.priority)
                        issue_dict.pop("priority", None)
                        retry = True
                    if "assignee" in errors:
                        logger.warning("Assignee '%s' is invalid. Retrying without assignee.", self.email)
                        issue_dict.pop("assignee", None)
                        retry = True
                        
                    if retry:
                        new_issue = self.jira_client.create_issue(fields=issue_dict)
                        return new_issue.key
                except Exception:
                    pass
            raise

    def _create_issue_link(self, story_key: str, original_issue_key: str) -> str | None:
        """Create an issue link for traceability. Tries configured type, then falls back.

        Parameters
        ----------
        story_key:
            The newly created story key.
        original_issue_key:
            The original issue key to link to.

        Returns
        -------
        str | None
            The link type name that was successfully used, or None.
        """
        # Try specified/configured project link types first, falling back to standard ones
        link_types_to_try = ["added to idea", "Relates", "Relates to", "Reference"]
        last_err = None
        for link_type in link_types_to_try:
            try:
                self.jira_client.create_issue_link(
                    type=link_type,
                    inwardIssue=story_key,
                    outwardIssue=original_issue_key,
                    comment={
                        "body": f"Generated from {original_issue_key} by BA Accelerator"
                    }
                )
                logger.info("Created issue link: %s (%s) %s", story_key, link_type, original_issue_key)
                return link_type
            except Exception as exc:
                last_err = exc
                continue
                
        logger.warning(
            "Failed to create issue link %s → %s using attempted link types. Last error: %s", 
            story_key, 
            original_issue_key, 
            last_err
        )
        return None
