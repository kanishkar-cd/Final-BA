from __future__ import annotations

import asyncio
from pathlib import Path

from app.parsers.parser_factory import ParserFactory
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DocumentImportService:
    """Validates and imports documents for the preprocessing pipeline.

    Supports two input modes:

    1. **Local file path** — a Path or string pointing to a .pdf / .docx / .txt file.
    2. **MCP source identifier** — a prefixed string that routes to the MCP
       enterprise connector layer and returns plain ``raw_text``:

       - ``"jira:<issue_key>"``           — fetch one Jira issue
       - ``"jira:<issue_key>,comments"``  — fetch issue + comments
       - ``"confluence:<page_id>"``       — fetch one Confluence page

       The ``raw_text`` returned by the MCP connector is passed directly to
       the ingestion pipeline and then to **Agent-1 (RequirementAnalysisAgent)**.
       No metadata is forwarded.
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xlsx", ".xls", ".ppt", ".pptx", ".txt"}

    async def import_document(self, file_path: str | Path) -> str:
        """Return extracted plain text for a local file or an MCP source."""
        path_str = str(file_path)

        # ── MCP source identifiers ────────────────────────────────────────────
        if path_str.startswith("sharepoint:"):
            return await self._fetch_from_mcp("sharepoint", path_str[len("sharepoint:"):])

        if path_str.startswith("jira:"):
            return await self._fetch_from_mcp("jira", path_str[len("jira:"):])

        if path_str.startswith("confluence:"):
            return await self._fetch_from_mcp("confluence", path_str[len("confluence:"):])
            
        if path_str.startswith("ado:"):
            return await self._fetch_from_mcp("ado", path_str[len("ado:"):])

        if path_str.startswith("onedrive:"):
            return await self._fetch_from_onedrive(path_str[len("onedrive:"):])

        # ── Local file ────────────────────────────────────────────────────────
        path = Path(file_path)

        if not path.exists():
            logger.error("Document not found: %s", path)
            raise FileNotFoundError(f"Document not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            logger.error("Unsupported file type: %s", ext)
            raise ValueError(
                f"Unsupported file type: {ext}. "
                f"Supported: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        try:
            parser = ParserFactory.create(str(path))
            extracted_text = await parser.parse(str(path))
        except Exception as exc:
            logger.exception("Parsing failed for %s", path)
            raise RuntimeError(f"Failed to parse document: {path}") from exc

        logger.info("Imported local document: %s", path)
        return extracted_text

    async def _fetch_from_mcp(self, source: str, identifier: str) -> str:
        """Call the MCP connector and return only raw_text.

        Parameters
        ----------
        source:
            ``"jira"``, ``"confluence"``, or ``"ado"``
        identifier:
            Issue key (Jira), page ID (Confluence), or ado:<org>:<project>:<pat>:<id>
        """
        from mcp_server.schemas.mcp_schemas import (
            ConfluenceFetchRequest,
            JiraFetchRequest,
            AdoFetchRequest,
            MCPFetchRequest,
        )
        from mcp_server.app import _dispatch

        logger.info("Fetching raw_text from MCP source='%s' identifier='%s'", source, identifier)

        if source == "sharepoint":
            parts = identifier.split("|", 1)
            site_url = parts[0]
            folder_path = parts[1] if len(parts) > 1 else ""
            from mcp_server.services.sharepoint_service import SharePointService
            service = SharePointService(site_url=site_url, folder_path=folder_path)
            res = service.fetch_folder_documents()
            return res.raw_text

        if source == "jira":
            include_comments = False
            issue_key = identifier
            if "," in identifier:
                issue_key, flag = identifier.split(",", 1)
                include_comments = "comment" in flag.lower()
            request = MCPFetchRequest(
                source="jira",
                jira=JiraFetchRequest(
                    issue_key=issue_key,
                    include_comments=include_comments,
                ),
            )
        elif source == "ado":
            parts = identifier.split(":", 3)
            if len(parts) != 4:
                raise ValueError("ADO identifier must be format 'org:project:pat:id'")
            org, proj, pat, wid = parts
            request = MCPFetchRequest(
                source="ado",
                ado=AdoFetchRequest(
                    org=org,
                    project=proj,
                    pat=pat,
                    work_item_id=wid
                )
            )
        else:  # confluence
            request = MCPFetchRequest(
                source="confluence",
                confluence=ConfluenceFetchRequest(page_id=identifier),
            )

        # _dispatch is synchronous — run it off the event loop thread
        raw_text: str = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch, request
        )

        logger.info(
            "MCP source='%s' returned %d characters of raw_text",
            source, len(raw_text),
        )
        return raw_text

    async def _fetch_from_onedrive(self, url: str) -> str:
        """Download public OneDrive file/doc, save it locally, parse it, and return its text."""
        # Check for simulated mock files first
        if "mock-PRD_PaymentGateway_v2.docx" in url:
            return "PRD Payment Gateway System:\nRequirements:\n1. The system must process Visa, Mastercard, and Amex credit card payments.\n2. The system must support multi-currency checkouts (USD, EUR, GBP, CAD).\nRules:\n1. Transaction fees must be calculated at 2.5% per credit card transaction.\n2. Decline notifications must be sent to the user instantly."
        elif "mock-User_Feedback_Report.txt" in url:
            return "User Feedback Report:\nRequirements:\n1. Provide a toggle to switch between Light and Dark mode themes.\n2. Dashboard analytics screens must load in less than 1.5 seconds.\n3. Send push/email notifications once the user story generation completes."
        elif "mock-BAA_System_Architecture.pdf" in url:
            return "BAA System Architecture Document:\nRequirements:\n1. Use Qdrant vector database for dense requirements embeddings.\n2. Implement a hybrid retrieval pipeline using Reciprocal Rank Fusion (RRF).\n3. Keep orchestrator agents stateful and serializable in PostgreSQL."
        elif "mock-API_Endpoints_Spec.md" in url:
            return "API Specification Document:\nRequirements:\n1. Support GET /api/onedrive/files to list files in nested directories.\n2. Support POST /api/onedrive/import to download and parse file content.\n3. Authenticate requests securely using delegated permissions."

        from pathlib import Path
        from uuid import uuid4
        
        content, filename, extension = await self._download_onedrive_file(url)
        
        upload_dir = Path(__file__).resolve().parents[2] / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = upload_dir / f"{uuid4().hex}{extension}"
        stored_path.write_bytes(content)
        
        try:
            parser = ParserFactory.create(str(stored_path))
            extracted_text = await parser.parse(str(stored_path))
        except Exception as exc:
            logger.exception("Parsing failed for downloaded OneDrive file %s", stored_path)
            raise RuntimeError(f"Failed to parse downloaded OneDrive document: {exc}") from exc
            
        return extracted_text

    async def _download_onedrive_file(self, url: str) -> tuple[bytes, str, str]:
        import httpx
        import re
        from pathlib import Path
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.head(url)
            final_url = str(response.url)
            
            # Personal OneDrive live.com sharing link
            if "onedrive.live.com" in final_url:
                download_url = final_url.replace("/redir", "/download").replace("/view.aspx", "/download")
                if "download" not in download_url:
                    download_url += "&download=1" if "?" in download_url else "?download=1"
            # SharePoint / OneDrive for Business link
            elif ".sharepoint.com" in final_url:
                if "?" in final_url:
                    if "download=1" not in final_url:
                        download_url = final_url + "&download=1"
                    else:
                        download_url = final_url
                else:
                    download_url = final_url + "?download=1"
            else:
                download_url = final_url + ("&download=1" if "?" in final_url else "?download=1")
                
            logger.info("Downloading OneDrive file from URL: %s", download_url)
            
            resp = await client.get(download_url)
            
            # Check if the download redirected to a login page or returned login HTML
            final_resp_url = str(resp.url)
            content_type = resp.headers.get("content-type", "").lower()
            
            is_auth_redirect = (
                "login.microsoftonline.com" in final_resp_url
                or "login.live.com" in final_resp_url
                or "login.windows.net" in final_resp_url
                or "/_layouts/15/casignin.aspx" in final_resp_url
            )
            
            if resp.status_code in (401, 403) or is_auth_redirect or (resp.status_code == 200 and "text/html" in content_type):
                raise PermissionError(
                    "This OneDrive link requires organizational authentication. "
                    "Since application registration is not configured, please ensure "
                    "the sharing link is set to 'Anyone with the link' or upload the file locally."
                )
                
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to download OneDrive file. HTTP Status: {resp.status_code}")
                
            content_type = resp.headers.get("content-type", "")
            content_disposition = resp.headers.get("content-disposition", "")
            
            extension = ".txt"
            filename = "onedrive_doc"
            
            fn_match = re.search(r'filename="?([^";]+)"?', content_disposition)
            if fn_match:
                filename = fn_match.group(1)
                extension = Path(filename).suffix.lower()
            else:
                if "application/pdf" in content_type:
                    extension = ".pdf"
                elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type:
                    extension = ".docx"
                elif "text/plain" in content_type:
                    extension = ".txt"
                filename = f"onedrive_doc{extension}"
                
            return resp.content, filename, extension
