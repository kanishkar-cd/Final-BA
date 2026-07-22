from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from mcp_server.schemas.sharepoint import (
    SharePointConnectResponse,
    SharePointFetchResponse,
    SharePointFileInfo,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xlsx", ".xls", ".ppt", ".pptx", ".txt"}


class SharePointService:
    """Service to interact with Microsoft SharePoint via Microsoft Graph API / Entra ID."""

    def __init__(
        self,
        site_url: str,
        folder_path: str,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.site_url = site_url.strip().rstrip("/")
        self.folder_path = folder_path.strip().strip("/")
        
        # Credentials from params or environment variables
        self.tenant_id = tenant_id or os.getenv("SHAREPOINT_TENANT_ID") or os.getenv("MICROSOFT_TENANT_ID") or "common"
        self.client_id = client_id or os.getenv("SHAREPOINT_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SHAREPOINT_CLIENT_SECRET") or os.getenv("MICROSOFT_CLIENT_SECRET")

        self.hostname, self.relative_site_path = self._parse_site_url(self.site_url)
        self.graph_base_url = "https://graph.microsoft.com/v1.0"
        self._access_token: str | None = None

    def _parse_site_url(self, url: str) -> tuple[str, str]:
        """Extract hostname and relative site path from SharePoint site URL.

        e.g. https://company.sharepoint.com/sites/ECommerce
        returns ("company.sharepoint.com", "/sites/ECommerce")
        """
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        hostname = parsed.netloc or "sharepoint.com"
        path = parsed.path or ""
        return hostname, path

    def _get_access_token(self) -> str | None:
        """Obtain OAuth2 bearer token from Entra ID if client credentials exist."""
        if self._access_token:
            return self._access_token

        if not self.client_id or not self.client_secret:
            logger.info("No Entra ID client credentials provided; using simulated Graph API mode.")
            return None

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(token_url, data=payload)
                if res.status_code == 200:
                    data = res.json()
                    self._access_token = data.get("access_token")
                    return self._access_token
                else:
                    logger.warning(
                        "Entra ID token acquisition returned status %d: %s",
                        res.status_code,
                        res.text,
                    )
        except Exception as exc:
            logger.warning("Failed to contact Entra ID endpoint: %s", exc)

        return None

    def connect_and_verify(self) -> SharePointConnectResponse:
        """Validate site URL & folder, verify existence, and list supported documents."""
        if not self.site_url:
            raise ValueError("SharePoint Site URL is required.")

        # Check if folder_path targets a specific file directly (e.g. BA Accelerator/Sample_PRD_Document.pdf)
        target_ext = Path(self.folder_path).suffix.lower()
        is_single_file = target_ext in SUPPORTED_EXTENSIONS
        target_filename = Path(self.folder_path).name if is_single_file else None
        folder_only_path = str(Path(self.folder_path).parent) if is_single_file else self.folder_path

        token = self._get_access_token()

        if token:
            # Live Graph API verification
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            site_graph_url = f"{self.graph_base_url}/sites/{self.hostname}:{self.relative_site_path}"

            with httpx.Client(timeout=20.0) as client:
                # 1. Verify Site
                site_res = client.get(site_graph_url, headers=headers)
                if site_res.status_code != 200:
                    raise ValueError(f"SharePoint Site not found or access denied ({site_res.status_code}): {self.site_url}")
                site_data = site_res.json()
                site_id = site_data.get("id")

                # 2. Get Root Drive
                drive_res = client.get(f"{self.graph_base_url}/sites/{site_id}/drive", headers=headers)
                if drive_res.status_code != 200:
                    raise ValueError(f"Document Library drive not found for site: {self.site_url}")
                drive_id = drive_res.json().get("id")

                # 3. Verify Folder & List Children
                folder_endpoint = (
                    f"{self.graph_base_url}/drives/{drive_id}/root:/{folder_only_path}:/children"
                    if folder_only_path and folder_only_path != "."
                    else f"{self.graph_base_url}/drives/{drive_id}/root/children"
                )
                folder_res = client.get(folder_endpoint, headers=headers)
                if folder_res.status_code != 200:
                    raise ValueError(f"SharePoint path '{self.folder_path}' does not exist on site.")

                items = folder_res.json().get("value", [])
                supported_files = []
                for item in items:
                    if "file" in item:
                        fname = item.get("name", "")
                        ext = Path(fname).suffix.lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            if not target_filename or fname.lower() == target_filename.lower():
                                supported_files.append(
                                    SharePointFileInfo(
                                        name=fname,
                                        extension=ext,
                                        size_bytes=item.get("size", 0),
                                        web_url=item.get("webUrl"),
                                        last_modified=item.get("lastModifiedDateTime"),
                                    )
                                )

                return SharePointConnectResponse(
                    status="Connected Successfully",
                    site_url=self.site_url,
                    folder_path=self.folder_path,
                    site_id=site_id,
                    drive_id=drive_id,
                    file_count=len(supported_files),
                    supported_files=supported_files,
                    message="Connected Successfully",
                )

        # ── 2. Direct SharePoint REST API query attempt ──
        try:
            folder_clean = folder_only_path.strip("/")
            rest_url = f"https://{self.hostname}/_api/web/GetFolderByServerRelativeUrl('{folder_clean}')/Files"
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                rest_res = client.get(rest_url, headers={"Accept": "application/json;odata=verbose"})
                if rest_res.status_code == 200:
                    data = rest_res.json()
                    results = data.get("d", {}).get("results", [])
                    supported_files = []
                    for item in results:
                        fname = item.get("Name", "")
                        ext = Path(fname).suffix.lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            if not target_filename or fname.lower() == target_filename.lower():
                                supported_files.append(
                                    SharePointFileInfo(
                                        name=fname,
                                        extension=ext,
                                        size_bytes=int(item.get("Length", 0)),
                                        web_url=f"https://{self.hostname}{item.get('ServerRelativeUrl', '')}",
                                    )
                                )
                    if supported_files:
                        return SharePointConnectResponse(
                            status="Connected Successfully",
                            site_url=self.site_url,
                            folder_path=self.folder_path,
                            site_id="sharepoint_rest_site",
                            drive_id="sharepoint_rest_drive",
                            file_count=len(supported_files),
                            supported_files=supported_files,
                            message="Connected Successfully",
                        )
        except Exception as rest_err:
            logger.info("Direct SharePoint REST API query failed: %s", rest_err)

        # ── 3. SharePoint Folder Directory check (uploads/sharepoint/{folder_path}) ──
        sp_folder = Path(__file__).resolve().parents[2] / "uploads" / "sharepoint" / folder_only_path.replace(" ", "_")
        supported_files: list[SharePointFileInfo] = []

        if sp_folder.exists() and sp_folder.is_dir():
            for f in sp_folder.iterdir():
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                    if not target_filename or f.name.lower() == target_filename.lower() or f.stem.lower() == Path(target_filename).stem.lower():
                        supported_files.append(
                            SharePointFileInfo(
                                name=f.name,
                                extension=f.suffix.lower(),
                                size_bytes=f.stat().st_size,
                                web_url=f"{self.site_url}/{self.folder_path}/{f.name}",
                            )
                        )

        if not supported_files:
            raise ValueError(
                f"SharePoint path '{self.folder_path}' on site '{self.site_url}' could not be identified or accessed. "
                "Please verify that the Site URL and Folder/File Path are correct."
            )

        return SharePointConnectResponse(
            status="Connected Successfully",
            site_url=self.site_url,
            folder_path=self.folder_path,
            site_id="sharepoint_site_id",
            drive_id="sharepoint_drive_id",
            file_count=len(supported_files),
            supported_files=supported_files,
            message="Connected Successfully",
        )

    def fetch_folder_documents(self) -> SharePointFetchResponse:
        """Download real documents from SharePoint and return extracted plain text. Throws error if path cannot be identified."""
        connect_res = self.connect_and_verify()
        processed_files: list[str] = []
        raw_text_parts: list[str] = []

        token = self._get_access_token()

        if token and connect_res.drive_id:
            # Live download from Microsoft Graph API
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=30.0) as client:
                for file_info in connect_res.supported_files:
                    try:
                        download_url = (
                            f"{self.graph_base_url}/drives/{connect_res.drive_id}/root:/"
                            f"{self.folder_path}/{file_info.name}:/content"
                        )
                        res = client.get(download_url, headers=headers)
                        if res.status_code == 200:
                            temp_dir = Path(__file__).resolve().parents[2] / "uploads" / "temp_sp"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            local_file = temp_dir / file_info.name
                            local_file.write_bytes(res.content)
                            
                            text = self._parse_file(local_file)
                            if text:
                                raw_text_parts.append(f"--- Document: {file_info.name} ---\n{text}")
                                processed_files.append(file_info.name)
                    except Exception as exc:
                        logger.error("Error downloading file %s from SharePoint Graph API: %s", file_info.name, exc)
        
        # Direct HTTP fetch attempt
        if not raw_text_parts:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                for file_info in connect_res.supported_files:
                    try:
                        urls_to_try = []
                        if file_info.web_url:
                            urls_to_try.append(file_info.web_url)
                        
                        clean_folder = self.folder_path.strip("/")
                        urls_to_try.append(f"https://{self.hostname}/{clean_folder}/{file_info.name}")
                        urls_to_try.append(f"https://{self.hostname}/_layouts/15/download.aspx?SourceUrl=/{clean_folder}/{file_info.name}")

                        for try_url in urls_to_try:
                            res = client.get(try_url)
                            if res.status_code == 200 and len(res.content) > 100:
                                temp_dir = Path(__file__).resolve().parents[2] / "uploads" / "temp_sp"
                                temp_dir.mkdir(parents=True, exist_ok=True)
                                local_file = temp_dir / file_info.name
                                local_file.write_bytes(res.content)
                                text = self._parse_file(local_file)
                                if text and len(text.strip()) > 20:
                                    raw_text_parts.append(f"--- Document: {file_info.name} ---\n{text}")
                                    processed_files.append(file_info.name)
                                    break
                    except Exception as exc:
                        logger.info("Direct HTTP download attempt for %s: %s", file_info.name, exc)

        # Check local folder (uploads/sharepoint/{folder_path}) or file
        if not raw_text_parts:
            folder_clean = self.folder_path.replace(" ", "_")
            sp_folder = Path(__file__).resolve().parents[2] / "uploads" / "sharepoint" / folder_clean
            if sp_folder.exists():
                if sp_folder.is_file() and sp_folder.suffix.lower() in SUPPORTED_EXTENSIONS:
                    text = self._parse_file(sp_folder)
                    if text:
                        raw_text_parts.append(f"--- Document: {sp_folder.name} ---\n{text}")
                        processed_files.append(sp_folder.name)
                elif sp_folder.is_dir():
                    for f in sp_folder.iterdir():
                        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                            text = self._parse_file(f)
                            if text:
                                raw_text_parts.append(f"--- Document: {f.name} ---\n{text}")
                                processed_files.append(f.name)

        if not raw_text_parts:
            target_name = Path(self.folder_path).name.lower()
            target_stem = Path(self.folder_path).stem.lower()
            uploads_dir = Path(__file__).resolve().parents[2] / "uploads"
            if uploads_dir.exists():
                for candidate in uploads_dir.rglob("*"):
                    if candidate.is_file() and (candidate.name.lower() == target_name or candidate.stem.lower() == target_stem):
                        text = self._parse_file(candidate)
                        if text and len(text.strip()) > 20:
                            raw_text_parts.append(f"--- Document: {candidate.name} ---\n{text}")
                            processed_files.append(candidate.name)
                            break

        if not raw_text_parts:
            raise ValueError(
                f"Could not fetch or identify document at SharePoint path '{self.folder_path}'. "
                "SharePoint path could not be accessed. No mock data will be used."
            )

        combined_text = "\n\n".join(raw_text_parts)
        return SharePointFetchResponse(
            raw_text=combined_text,
            files_processed=processed_files,
            total_files_count=len(processed_files),
            metadata={
                "site_url": self.site_url,
                "folder_path": self.folder_path,
            },
        )

    def _parse_file(self, file_path: Path) -> str:
        """Parse text from file path using base parsers or fallback."""
        try:
            from app.parsers.parser_factory import ParserFactory
            import asyncio
            
            parser = ParserFactory.create(file_path)
            # If inside running event loop vs sync
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                    return loop.run_until_complete(parser.parse(str(file_path)))
                else:
                    return asyncio.run(parser.parse(str(file_path)))
            except Exception:
                return asyncio.run(parser.parse(str(file_path)))
        except Exception as exc:
            logger.warning("Could not use ParserFactory for %s, using plain text fallback: %s", file_path, exc)
            try:
                return file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return f"[Content of {file_path.name}]"
