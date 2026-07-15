from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from app.schemas.user_story import UserStory


class JiraIssueExport(BaseModel):
    """
    B5.2: Jira-ready story template.
    Matches the expected import format for Jira REST API.
    """
    project_key: str
    summary: str
    description: str
    issue_type: str = "Story"
    labels: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class AzureDevOpsWorkItemExport(BaseModel):
    """
    B5.2: Azure DevOps-ready story template.
    Matches the expected import format for Azure DevOps REST API.
    """
    title: str
    description: str
    work_item_type: str = "User Story"
    tags: str = ""
    acceptance_criteria: str = ""


def _format_acceptance_criteria_for_jira(story: UserStory) -> str:
    if not story.acceptance_criteria:
        return ""
    lines = ["*Acceptance Criteria:*"]
    for ac in story.acceptance_criteria:
        lines.append(f"* {ac.description}")
        if ac.source_refs:
            lines.append(f"  _(Sources: {', '.join(ac.source_refs)})_")
    return "\n".join(lines)


def map_story_to_jira(story: UserStory, project_key: str) -> JiraIssueExport:
    """Maps a UserStory to a Jira Issue payload."""
    
    desc_lines = [
        f"**Goal**: {story.goal}",
        f"**Business Value**: {story.business_value}",
        "",
        "**User Story**: ",
        story.user_story,
        "",
        _format_acceptance_criteria_for_jira(story),
        "",
        "*Definition of Done:*",
        story.definition_of_done or "N/A"
    ]
    
    if story.assumptions:
        desc_lines.extend(["", "*Assumptions:*"] + [f"- {a}" for a in story.assumptions])
        
    if story.risks:
        desc_lines.extend(["", "*Risks:*"] + [f"- {r}" for r in story.risks])

    labels = ["ba-accelerator"]
    if story.persona:
        labels.append(story.persona.replace(" ", "-").lower())

    return JiraIssueExport(
        project_key=project_key,
        summary=story.name,
        description="\n".join(desc_lines),
        labels=labels,
        custom_fields={
            "traceability_id": story.id,
            "epic_id": story.epic_id
        }
    )


def map_story_to_azure_devops(story: UserStory) -> AzureDevOpsWorkItemExport:
    """Maps a UserStory to an Azure DevOps Work Item payload."""
    
    desc_lines = [
        f"<b>Goal:</b> {story.goal}<br>",
        f"<b>Business Value:</b> {story.business_value}<br><br>",
        "<b>User Story:</b><br>",
        story.user_story,
        "<br><br><b>Definition of Done:</b><br>",
        story.definition_of_done or "N/A"
    ]
    
    ac_lines = []
    for ac in story.acceptance_criteria:
        ac_lines.append(f"<li>{ac.description}")
        if ac.source_refs:
            ac_lines.append(f" <i>(Sources: {', '.join(ac.source_refs)})</i>")
        ac_lines.append("</li>")
        
    ac_html = "<ul>" + "".join(ac_lines) + "</ul>" if ac_lines else ""

    tags = ["ba-accelerator"]
    if story.persona:
        tags.append(story.persona.replace(" ", "-").lower())

    return AzureDevOpsWorkItemExport(
        title=story.name,
        description="".join(desc_lines),
        tags="; ".join(tags),
        acceptance_criteria=ac_html
    )
