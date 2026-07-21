"""Export service for Azure DevOps."""

from __future__ import annotations

import logging
import httpx
import base64

from export.models import ExportRequest, ExportResponse, ExportStatus, ExportFormat
from mcp_server.services.azure_service import AzureService

logger = logging.getLogger(__name__)

class AzureExporter:
    """Exports generated user stories to Azure DevOps as Work Items."""

    def __init__(self, organization: str, project: str, pat_token: str):
        self.organization = organization
        self.project = project
        self.pat_token = pat_token
        self.base_url = f"https://dev.azure.com/{organization}/{project}/_apis"
        self.api_version = "7.1"

    def _get_headers(self) -> dict:
        auth_string = f":{self.pat_token}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        return {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json-patch+json",
        }

    def _format_description(self, story) -> str:
        """Format the user story description into HTML."""
        lines = []
        if story.user_story:
            lines.append(f"<b>User Story:</b><br>{story.user_story}<br><br>")
        
        lines.append(f"<b>Description:</b><br>{story.description.replace(chr(10), '<br>')}<br>")
        return "".join(lines)
        
    def _format_acceptance_criteria(self, story) -> str:
        if not story.acceptance_criteria:
            return ""
        html = "<ul>"
        for ac in story.acceptance_criteria:
            html += f"<li>{ac}</li>"
        html += "</ul>"
        return html

    def export(self, request: ExportRequest) -> ExportResponse:
        """Export stories to Azure DevOps synchronously."""
        logger.info(f"Starting Azure DevOps export for {len(request.stories)} stories.")
        
        created_items = []
        errors = []

        with httpx.Client() as client:
            for story in request.stories:
                try:
                    url = f"{self.base_url}/wit/workitems/$User%20Story?api-version={self.api_version}"
                    
                    patch_doc = [
                        {
                            "op": "add",
                            "path": "/fields/System.Title",
                            "value": story.title
                        },
                        {
                            "op": "add",
                            "path": "/fields/System.Description",
                            "value": self._format_description(story)
                        }
                    ]
                    
                    ac_html = self._format_acceptance_criteria(story)
                    if ac_html:
                        patch_doc.append({
                            "op": "add",
                            "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria",
                            "value": ac_html
                        })
                        
                    if story.story_points is not None:
                        patch_doc.append({
                            "op": "add",
                            "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
                            "value": story.story_points
                        })

                    # Link to parent Work Item if provided
                    parent_id = request.metadata.get("work_item_id")
                    if parent_id:
                        patch_doc.append({
                            "op": "add",
                            "path": "/relations/-",
                            "value": {
                                "rel": "System.LinkTypes.Hierarchy-Reverse",
                                "url": f"{self.base_url}/wit/workitems/{parent_id}",
                                "attributes": {
                                    "name": "Parent"
                                }
                            }
                        })

                    response = client.post(url, headers=self._get_headers(), json=patch_doc)
                    
                    if response.status_code in (200, 201):
                        data = response.json()
                        created_items.append({
                            "story_id": story.story_id,
                            "ado_id": data.get("id"),
                            "url": data.get("_links", {}).get("html", {}).get("href")
                        })
                    else:
                        logger.error(f"Failed to create ADO item for {story.title}: {response.text}")
                        errors.append(f"Failed to create '{story.title}': {response.text}")
                        
                except Exception as e:
                    logger.exception(f"Exception creating ADO item for {story.title}")
                    errors.append(f"Error for '{story.title}': {str(e)}")

        if not created_items and errors:
            return ExportResponse(
                export_id=f"export-{request.project_name}",
                status=ExportStatus.FAILED,
                format=ExportFormat.ADO,
                error_message="; ".join(errors),
                story_count=0
            )

        return ExportResponse(
            export_id=f"export-{request.project_name}",
            status=ExportStatus.COMPLETED if not errors else ExportStatus.IN_PROGRESS,
            format=ExportFormat.ADO,
            download_url=created_items[0]["url"] if created_items else None,
            story_count=len(created_items),
            export_metadata={"created_items": created_items, "errors": errors}
        )
