from fastapi import APIRouter, HTTPException
from mcp_server.schemas.sharepoint import (
    SharePointConnectRequest,
    SharePointConnectResponse,
    SharePointFetchRequest,
    SharePointFetchResponse,
)
from mcp_server.services.sharepoint_service import SharePointService

router = APIRouter(prefix="/mcp/connectors/sharepoint", tags=["SharePoint Connector"])


def _build_path(document_library: str | None, folder_path: str | None, file_name: str | None) -> str:
    parts = []
    if document_library and document_library.strip():
        parts.append(document_library.strip("/"))
    if folder_path and folder_path.strip():
        parts.append(folder_path.strip("/"))
    if file_name and file_name.strip():
        parts.append(file_name.strip("/"))
    return "/".join(parts) if parts else (folder_path or "")


@router.post("/connect", response_model=SharePointConnectResponse)
def connect_sharepoint(request: SharePointConnectRequest) -> SharePointConnectResponse:
    """Validate SharePoint Site URL, Document Library, Folder Path, and File Name."""
    try:
        full_path = _build_path(request.document_library, request.folder_path, request.file_name)
        service = SharePointService(
            site_url=request.site_url,
            folder_path=full_path,
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            client_secret=request.client_secret,
        )
        return service.connect_and_verify()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SharePoint connection failed: {e}")


@router.post("/fetch", response_model=SharePointFetchResponse)
def fetch_sharepoint_documents(request: SharePointFetchRequest) -> SharePointFetchResponse:
    """Download supported files in the SharePoint document path and return extracted plain text."""
    try:
        full_path = _build_path(request.document_library, request.folder_path, request.file_name)
        service = SharePointService(
            site_url=request.site_url,
            folder_path=full_path,
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            client_secret=request.client_secret,
        )
        return service.fetch_folder_documents()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SharePoint document fetch failed: {e}")
