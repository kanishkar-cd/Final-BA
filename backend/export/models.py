"""Data models for the export module."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    """Supported export formats."""

    WORD = "word"
    PDF = "pdf"
    JIRA = "jira"
    CONFLUENCE = "confluence"
    ADO = "ado"


class ExportStatus(str, Enum):
    """Export job status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class StoryExportData(BaseModel):
    """User story data for export."""

    story_id: str
    title: str
    user_story: str | None = None
    description: str
    acceptance_criteria: list[Any] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    dependencies: list[Any] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)
    priority: str | None = None
    story_points: int | None = None
    epic: str | None = None
    feature: str | None = None
    epic_mapping: list[Any] = Field(default_factory=list)
    traceability: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    assignee: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    """Request to export user stories."""

    format: ExportFormat
    stories: list[StoryExportData]
    project_name: str = Field(default="Project")
    include_metadata: bool = Field(default=True)
    template_name: str | None = None
    output_filename: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExportResponse(BaseModel):
    """Response from an export operation."""

    export_id: str
    status: ExportStatus
    format: ExportFormat
    file_path: str | None = None
    download_url: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    story_count: int = 0
    export_metadata: dict[str, Any] = Field(default_factory=dict)


class JiraExportConfig(BaseModel):
    """Configuration for Jira export."""

    project_key: str
    issue_type: str = Field(default="Story")
    base_url: str
    email: str
    api_token: str
    assign_to_me: bool = Field(default=False)
    default_priority: str = Field(default="Medium")


class ConfluenceExportConfig(BaseModel):
    """Configuration for Confluence export."""

    space_key: str
    parent_page_id: str | None = None
    base_url: str
    email: str
    api_token: str
    include_toc: bool = Field(default=True)
    page_title_prefix: str = Field(default="")
