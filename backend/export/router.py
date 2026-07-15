"""FastAPI router for Export module, expecting Agent-4 validated output."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from export.export_service import ExportService
from export.models import ExportFormat, ExportRequest, StoryExportData, ExportStatus

router = APIRouter(tags=["Export"])

export_service = ExportService()


class Agent4Payload(BaseModel):
    """Expects the full Agent-4 ApiResponse or a similarly structured payload."""
    data: dict[str, Any] | None = None

    @property
    def raw_stories(self) -> list[dict[str, Any]]:
        if self.data and "stories" in self.data:
            return self.data["stories"]
        return []


def _map_agent4_to_story_export_data(story_dict: dict[str, Any]) -> StoryExportData:
    """Map Agent-4 UserStory dict to StoryExportData."""
    # Handle Acceptance Criteria (might be list of strings or list of dicts)
    raw_ac = story_dict.get("acceptance_criteria", [])
    ac_list = []
    for ac in raw_ac:
        if isinstance(ac, dict) and "description" in ac:
            ac_list.append(ac["description"])
        else:
            ac_list.append(ac)
            
    # Priority
    priority = story_dict.get("priority")
    if hasattr(priority, "value"):
        priority = priority.value

    return StoryExportData(
        story_id=story_dict.get("id") or story_dict.get("story_id", "UNKNOWN"),
        title=story_dict.get("title", "Untitled"),
        user_story=story_dict.get("user_story"),
        description=story_dict.get("description", ""),
        acceptance_criteria=ac_list,
        business_rules=story_dict.get("business_rules", []),
        dependencies=story_dict.get("dependencies", []),
        definition_of_done=story_dict.get("definition_of_done", []),
        priority=str(priority) if priority else None,
        story_points=story_dict.get("story_points"),
        epic=story_dict.get("epic_id"),
        feature=story_dict.get("feature_id"),
        epic_mapping=story_dict.get("epic_mapping", []),
        traceability=story_dict.get("traceability", {}),
        metadata=story_dict.get("metadata", {}),
    )


@router.post("/word")
async def export_to_word(payload: Agent4Payload) -> Any:
    """Export validated Agent-4 output to Word."""
    stories = payload.raw_stories
    if not stories:
        raise HTTPException(status_code=400, detail="No stories found in Agent-4 payload data.")

    export_stories = [_map_agent4_to_story_export_data(s) for s in stories]
    
    request = ExportRequest(
        format=ExportFormat.WORD,
        stories=export_stories,
        project_name="Exported Stories"
    )
    
    response = export_service.export(request)
    if response.status == "failed":
        raise HTTPException(status_code=500, detail=response.error_message)
        
    return response


@router.post("/pdf")
async def export_to_pdf(payload: Agent4Payload) -> Any:
    """Export validated Agent-4 output to PDF."""
    stories = payload.raw_stories
    if not stories:
        raise HTTPException(status_code=400, detail="No stories found in Agent-4 payload data.")

    export_stories = [_map_agent4_to_story_export_data(s) for s in stories]
    
    request = ExportRequest(
        format=ExportFormat.PDF,
        stories=export_stories,
        project_name="Exported Stories"
    )
    
    response = export_service.export(request)
    if response.status == "failed":
        raise HTTPException(status_code=500, detail=response.error_message)
        
    return response


import os
from dotenv import load_dotenv

@router.post("/jira")
async def export_to_jira(payload: Agent4Payload) -> Any:
    """Export validated Agent-4 output to Jira. Loads credentials from .env."""
    stories = payload.raw_stories
    if not stories:
        raise HTTPException(status_code=400, detail="No stories found in Agent-4 payload data.")

    # Dynamically reload .env to ensure fresh credentials are loaded
    load_dotenv(override=True)

    export_stories = [_map_agent4_to_story_export_data(s) for s in stories]
    
    # Extract metadata including original_issue_key if present
    request_metadata = {}
    if payload.data and "metadata" in payload.data:
        request_metadata = payload.data["metadata"]
    if payload.data and "original_issue_key" in payload.data:
        request_metadata["original_issue_key"] = payload.data["original_issue_key"]

    request = ExportRequest(
        format=ExportFormat.JIRA,
        stories=export_stories,
        project_name="Exported Stories",
        metadata=request_metadata
    )
    
    response = export_service.export(request)
    if response.status == "failed":
        raise HTTPException(status_code=500, detail=response.error_message)
        
    return response


@router.post("/confluence")
async def export_to_confluence(payload: Agent4Payload, page_id: str | None = None) -> Any:
    """Export validated Agent-4 output to Confluence as a single page."""
    stories = payload.raw_stories
    if not stories:
        raise HTTPException(status_code=400, detail="No stories found in Agent-4 payload data.")
    
    # Dynamically reload .env to ensure fresh credentials are loaded
    load_dotenv(override=True)

    export_stories = [_map_agent4_to_story_export_data(s) for s in stories]
    
    # Extract metadata including page_id if provided
    request_metadata = {}
    if payload.data and "metadata" in payload.data:
        request_metadata = payload.data["metadata"].copy()
    if page_id:
        request_metadata["page_id"] = page_id
    if payload.data and "workflow_id" in payload.data:
        request_metadata["workflow_id"] = payload.data["workflow_id"]

    request = ExportRequest(
        format=ExportFormat.CONFLUENCE,
        stories=export_stories,
        project_name="Exported Stories",
        metadata=request_metadata
    )
    
    response = export_service.export(request)
    
    if response.status == ExportStatus.FAILED:
        return {
            "status": "FAILED",
            "target": "confluence",
            "page_id": None,
            "page_url": None,
            "error": response.error_message
        }
        
    return {
        "status": "SUCCESS",
        "target": "confluence",
        "page_id": response.file_path,
        "page_url": response.download_url,
        "error": None
    }


