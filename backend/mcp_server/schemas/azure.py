from pydantic import BaseModel, Field
from typing import Dict, Any

class AzureWorkItemImportRequest(BaseModel):
    organization: str = Field(..., description="Azure DevOps Organization")
    project: str = Field(..., description="Azure DevOps Project")
    pat_token: str = Field(..., description="Personal Access Token")
    work_item_id: str = Field(..., description="Work Item ID")

class AzureWorkItemResponse(BaseModel):
    title: str = ""
    description: str = ""
    acceptance_criteria: str = ""
    type: str = ""
    formatted_text: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
