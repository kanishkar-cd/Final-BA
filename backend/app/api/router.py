from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.api.rag_router import router as rag_router
from app.api.story_router import router as user_story_router
from app.api.workflow_router import router as workflow_router
from app.services.import_service import DocumentImportService
from export.router import router as export_router

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")

import_service = DocumentImportService()
upload_dir = Path(__file__).resolve().parents[2] / "uploads"

api_router.include_router(user_story_router)
api_router.include_router(workflow_router)
api_router.include_router(rag_router)
api_router.include_router(export_router, prefix="/export")

# Register MCP enterprise connector routes.
# Wrapped so a missing dependency never crashes the full backend at startup.
try:
    from mcp_server.app import router as mcp_router
    api_router.include_router(mcp_router)
    logger.info("MCP enterprise connector routes registered at /api/mcp/*")
except Exception as _mcp_err:  # pragma: no cover
    logger.warning("MCP router could not be loaded — endpoints will be unavailable: %s", _mcp_err)


@api_router.post("/documents/import")
async def import_document(file: UploadFile = File(...)) -> JSONResponse:
    """Import an uploaded document and return the extracted text."""

    if not file.filename:
        return JSONResponse(
            status_code=400,
            content={"detail": "No file provided"},
        )

    suffix = Path(file.filename).suffix.lower()
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{uuid4().hex}{suffix}"
    stored_path.write_bytes(await file.read())

    try:
        extracted_text = await import_service.import_document(stored_path)

    except (FileNotFoundError, ValueError) as exc:
        stored_path.unlink(missing_ok=True)
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    except RuntimeError as exc:
        stored_path.unlink(missing_ok=True)
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)},
        )

    return JSONResponse(
        content={
            "extracted_text": extracted_text,
            "file_path": str(stored_path.resolve()),
        }
    )
