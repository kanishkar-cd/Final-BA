from fastapi import APIRouter, HTTPException
from mcp_server.schemas.azure import AzureWorkItemImportRequest, AzureWorkItemResponse
from mcp_server.services.azure_service import AzureService

router = APIRouter(prefix="/connectors/azure", tags=["Azure DevOps"])

@router.post("/import/work-item", response_model=AzureWorkItemResponse)
def import_work_item(request: AzureWorkItemImportRequest):
    try:
        service = AzureService(
            organization=request.organization,
            project=request.project,
            pat_token=request.pat_token
        )
        return service.fetch_work_item(request.work_item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
