"""Google Drive connector — fetches files and returns only plain text.

Authenticates via OAuth2 using ``credentials/client_secret.json``.
A ``token.json`` is auto-generated on first authentication and reused
for subsequent requests.

Supported file formats: PDF, DOCX, TXT, and native Google Docs
(exported as ``text/plain``).

Metadata (file_name, file_id, mime_type, owner, modified_date, size) is
persisted to ``storage/metadata/{file_name}.json`` but is **never**
returned to the caller.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from mcp_server.auth.google_auth import get_google_credentials
from mcp_server.utils.metadata_store import save_metadata
from mcp_server.utils.text_utils import (
    extract_docx_text,
    extract_pdf_text,
    extract_txt_text,
)

logger = logging.getLogger("mcp_server.tools.gdrive")

# MIME types we can extract text from
_SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "application/vnd.google-apps.document",  # native Google Docs
}


class GoogleDriveConnector:
    """Connects to Google Drive and extracts plain text from files."""

    def __init__(self) -> None:
        from googleapiclient.discovery import build

        creds = get_google_credentials()
        self._service = build("drive", "v3", credentials=creds)
        logger.info("GoogleDriveConnector initialised.")

    # ── Public API ──────────────────────────────────────────────────────

    def fetch_file(self, file_id: str) -> str:
        """Download a single file and return its content as plain text.

        Parameters
        ----------
        file_id:
            The Google Drive file ID.

        Returns
        -------
        str
            Readable plain text only.
        """
        logger.info("Fetching Google Drive file: %s", file_id)

        # Get file metadata
        file_meta = (
            self._service.files()
            .get(fileId=file_id, fields="id,name,mimeType,owners,modifiedTime,size")
            .execute()
        )

        mime_type = file_meta.get("mimeType", "")
        file_name = file_meta.get("name", file_id)

        # Download / export content
        raw_text = self._download_text(file_id, mime_type)

        # Store metadata internally
        self._store_metadata(file_meta, file_name)

        return raw_text

    def search_files(self, query: str, *, max_results: int = 10) -> str:
        """Search Drive and return concatenated plain text for all matches.

        Parameters
        ----------
        query:
            Google Drive search query (e.g. ``"name contains 'requirements'"``).
        max_results:
            Maximum files to fetch.

        Returns
        -------
        str
            All matching files' text joined with separators.
        """
        logger.info("Searching Google Drive: %s (max %d)", query, max_results)

        results = (
            self._service.files()
            .list(
                q=query,
                pageSize=max_results,
                fields="files(id,name,mimeType,owners,modifiedTime,size)",
            )
            .execute()
        )

        files = results.get("files", [])
        all_texts: list[str] = []

        for f in files:
            fid = f["id"]
            mime = f.get("mimeType", "")
            if mime not in _SUPPORTED_MIME_TYPES:
                logger.info("Skipping unsupported mime %s for file %s", mime, fid)
                continue
            try:
                text = self.fetch_file(fid)
                if text:
                    all_texts.append(text)
            except Exception:
                logger.warning("Failed to fetch file %s during search", fid)

        return "\n\n---\n\n".join(all_texts)

    def list_files(self, *, max_results: int = 20) -> list[dict[str, str]]:
        """List files in Drive (for discovery — not part of the ingestion API).

        Returns a list of ``{"id": ..., "name": ..., "mimeType": ...}`` dicts.
        """
        results = (
            self._service.files()
            .list(
                pageSize=max_results,
                fields="files(id,name,mimeType)",
            )
            .execute()
        )
        return results.get("files", [])

    # ── Download helpers ────────────────────────────────────────────────

    def _download_text(self, file_id: str, mime_type: str) -> str:
        """Download or export a file and convert to plain text."""
        from googleapiclient.http import MediaIoBaseDownload

        # Native Google Docs → export as text/plain
        if mime_type == "application/vnd.google-apps.document":
            request = self._service.files().export_media(
                fileId=file_id, mimeType="text/plain"
            )
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue().decode("utf-8", errors="replace").strip()

        # Binary files — download raw bytes
        request = self._service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        data = buffer.getvalue()

        if mime_type == "application/pdf":
            return extract_pdf_text(data)
        elif mime_type == (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ):
            return extract_docx_text(data)
        elif mime_type == "text/plain":
            return extract_txt_text(data)
        else:
            logger.warning("Unsupported MIME type: %s — returning empty text", mime_type)
            return ""

    # ── Metadata (internal only) ────────────────────────────────────────

    def _store_metadata(self, file_meta: dict[str, Any], file_name: str) -> None:
        """Persist file metadata to storage/metadata/{file_name}.json."""
        owners = file_meta.get("owners", [])
        owner = owners[0].get("displayName", "") if owners else ""

        metadata = {
            "file_name": file_name,
            "file_id": file_meta.get("id", ""),
            "mime_type": file_meta.get("mimeType", ""),
            "owner": owner,
            "modified_date": str(file_meta.get("modifiedTime", "")),
            "size": str(file_meta.get("size", "")),
        }
        save_metadata(file_name, metadata)
