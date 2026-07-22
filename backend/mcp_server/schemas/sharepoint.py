from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class SharePointFileInfo(BaseModel):
    """Metadata for a file found in SharePoint."""

    name: str
    extension: str
    size_bytes: int = 0
    web_url: str | None = None
    last_modified: str | None = None


class SharePointConnectRequest(BaseModel):
    """Request to validate SharePoint site, document library, folder, and file path."""

    site_url: str = Field(
        ...,
        description="SharePoint Site URL, e.g. https://itclouddestinations.sharepoint.com",
    )
    document_library: str | None = Field(
        default=None,
        description="Document Library Name, e.g. BA Accelerator or Shared Documents",
    )
    folder_path: str | None = Field(
        default=None,
        description="Optional Folder Path inside Library, e.g. Requirements or PRD",
    )
    file_name: str | None = Field(
        default=None,
        description="Optional File Name, e.g. Sample_PRD_Document.pdf",
    )
    tenant_id: str | None = Field(default=None)
    client_id: str | None = Field(default=None)
    client_secret: str | None = Field(default=None)


class SharePointConnectResponse(BaseModel):
    """Response returned upon connecting to SharePoint."""

    status: str = Field(default="Connected Successfully")
    site_url: str
    folder_path: str
    site_id: str | None = None
    drive_id: str | None = None
    folder_id: str | None = None
    file_count: int = 0
    supported_files: list[SharePointFileInfo] = Field(default_factory=list)
    message: str = "Connected Successfully"


class SharePointFetchRequest(BaseModel):
    """Request to fetch documents and extract plain text."""

    site_url: str
    folder_path: str | None = None
    document_library: str | None = None
    file_name: str | None = None
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class SharePointFetchResponse(BaseModel):
    """Response containing extracted raw text from SharePoint documents."""

    raw_text: str
    files_processed: list[str] = Field(default_factory=list)
    total_files_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
