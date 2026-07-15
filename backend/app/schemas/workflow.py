from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkflowStartRequest(BaseModel):
    workflow_id: str = Field(
        default_factory=lambda: f"WF-{uuid4().hex[:8].upper()}",
        description="Optional unique identifier for this workflow run. Auto-generated if not provided."
    )
    file_path: str | Path | None = Field(
        default=None,
        description=(
            "The path or identifier of the document to import. Can be:\n"
            "1. **Local relative path**: E.g., 'sample_brd.txt' (looked up in backend workdir).\n"
            "2. **Local absolute path**: E.g., 'E:\\GP_BRD\\cd-se-accelerators\\backend\\sample_brd.txt' (fully qualified system path).\n"
            "3. **MCP enterprise connector identifier**: E.g., 'jira:KAN-2' or 'confluence:524289' to fetch text from corporate issue/wiki platforms."
        ),
        examples=["sample_brd.txt", "jira:KAN-2"]
    )
    document_id: str | None = Field(None, description="Optional document UUID reference.")
    project_id: str | None = Field(None, description="Optional project UUID reference.")
    confidence_threshold: float = Field(default=0.8, ge=0, le=1, description="Minimum confidence for story validation.")
    max_retry_attempts: int = Field(default=3, ge=0, le=5, description="Maximum number of refinement/agent retries.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom workflow execution metadata.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "workflow_id": "WF-AUTO",
                "file_path": "sample_brd.txt",
                "confidence_threshold": 0.8,
                "max_retry_attempts": 3,
                "metadata": {}
            }
        }
    }


class WorkflowStateResponse(BaseModel):
    workflow_id: str
    workflow_status: str
    state: dict[str, Any] = Field(default_factory=dict)


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    workflow_status: str
    failed_node: str | None = None
    last_error: dict[str, Any] | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
