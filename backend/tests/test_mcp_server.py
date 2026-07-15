from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.schemas.mcp_schemas import MCPFetchRequest, MCPFetchResponse
from mcp_server.utils.metadata_store import load_metadata
from app.services.import_service import DocumentImportService


@pytest.fixture
def mock_jira():
    with patch("mcp_server.tools.jira.os.getenv") as mock_env:
        # Mock credentials env
        mock_env.side_effect = lambda key, default="": {
            "JIRA_BASE_URL": "https://test-jira.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "token123",
        }.get(key, default)

        with patch("jira.JIRA") as mock_jira_cls:
            mock_client = MagicMock()
            mock_jira_cls.return_value = mock_client
            yield mock_client


@pytest.fixture
def mock_confluence():
    with patch("mcp_server.tools.confluence.os.getenv") as mock_env:
        # Mock credentials env
        mock_env.side_effect = lambda key, default="": {
            "CONFLUENCE_URL": "https://test-confluence.atlassian.net/wiki",
            "CONFLUENCE_EMAIL": "test@example.com",
            "CONFLUENCE_API_TOKEN": "token456",
        }.get(key, default)

        with patch("atlassian.Confluence") as mock_conf_cls:
            mock_client = MagicMock()
            mock_conf_cls.return_value = mock_client
            yield mock_client


@pytest.fixture
def mock_gdrive():
    with patch("mcp_server.auth.google_auth.get_google_credentials") as mock_get_creds:
        mock_get_creds.return_value = MagicMock()
        with patch("googleapiclient.discovery.build") as mock_build:
            mock_client = MagicMock()
            mock_build.return_value = mock_client
            yield mock_client


# ── Test Jira Connector ─────────────────────────────────────────────────────

def test_jira_fetch_issue(mock_jira):
    # Setup mock issue fields
    mock_issue = MagicMock()
    mock_issue.fields.summary = "Test Jira Issue"
    mock_issue.fields.description = "This is a detailed description of the issue."
    mock_issue.fields.reporter.displayName = "John Doe"
    mock_issue.fields.assignee.displayName = "Jane Smith"
    mock_issue.fields.created = "2026-07-08T10:00:00"
    mock_issue.fields.updated = "2026-07-08T11:00:00"
    mock_issue.fields.labels = ["test", "mcp"]
    mock_issue.fields.project.key = "PROJ"

    mock_jira.issue.return_value = mock_issue

    from mcp_server.tools.jira import JiraConnector
    connector = JiraConnector()
    text = connector.fetch_issue("PROJ-123", include_comments=False)

    assert "Summary: Test Jira Issue" in text
    assert "Description:\nThis is a detailed description of the issue." in text

    # Check that metadata was saved internally
    metadata = load_metadata("PROJ-123")
    assert metadata is not None
    assert metadata["issue_key"] == "PROJ-123"
    assert metadata["project"] == "PROJ"
    assert metadata["reporter"] == "John Doe"
    assert metadata["assignee"] == "Jane Smith"
    assert metadata["labels"] == ["test", "mcp"]


# ── Test Confluence Connector ───────────────────────────────────────────────

def test_confluence_fetch_page(mock_confluence):
    # Setup mock page
    mock_page = {
        "title": "Test Confluence Page",
        "space": {"key": "DS"},
        "version": {"number": 3, "when": "2026-07-08T12:00:00"},
        "history": {"createdDate": "2026-07-01T09:00:00", "createdBy": {"displayName": "Alice"}},
        "_links": {"base": "https://test-confluence.atlassian.net", "webui": "/wiki/spaces/DS/pages/123"},
        "body": {
            "storage": {
                "value": "<p>This is page content from storage format. <strong>Bold text</strong></p>"
            }
        }
    }
    mock_confluence.get_page_by_id.return_value = mock_page

    from mcp_server.tools.confluence import ConfluenceConnector
    connector = ConfluenceConnector()
    text = connector.fetch_page("123")

    assert "This is page content from storage format." in text
    assert "Bold text" in text

    # Check metadata
    metadata = load_metadata("123")
    assert metadata is not None
    assert metadata["page_id"] == "123"
    assert metadata["title"] == "Test Confluence Page"
    assert metadata["space"] == "DS"
    assert metadata["author"] == "Alice"
    assert metadata["version"] == 3


# ── Test Google Drive Connector ─────────────────────────────────────────────

def test_gdrive_fetch_google_doc(mock_gdrive):
    # Mock files().get().execute() for metadata
    mock_meta = {
        "id": "file123",
        "name": "Project Requirements Doc",
        "mimeType": "application/vnd.google-apps.document",
        "owners": [{"displayName": "Bob Owner"}],
        "modifiedTime": "2026-07-08T13:00:00",
        "size": "5000",
    }
    mock_gdrive.files.return_value.get.return_value.execute.return_value = mock_meta

    # Mock files().export_media().execute() or next_chunk() download loop
    with patch("googleapiclient.http.MediaIoBaseDownload") as mock_downloader_cls:
        mock_downloader = MagicMock()
        # Make the downloader loop finish in one go
        mock_downloader.next_chunk.return_value = (None, True)
        mock_downloader_cls.return_value = mock_downloader

        # We must mock the buffer write or content inside getvalue
        # Since _download_text writes to buffer in the download loop, let's patch next_chunk to write to buffer.
        def mock_next_chunk():
            mock_downloader_cls.call_args[0][0].write(b"Extracted text from Google Doc")
            return (None, True)
        mock_downloader.next_chunk.side_effect = mock_next_chunk

        from mcp_server.tools.gdrive import GoogleDriveConnector
        connector = GoogleDriveConnector()
        text = connector.fetch_file("file123")

        assert text == "Extracted text from Google Doc"

        # Check metadata
        metadata = load_metadata("Project Requirements Doc")
        assert metadata is not None
        assert metadata["file_id"] == "file123"
        assert metadata["file_name"] == "Project Requirements Doc"
        assert metadata["owner"] == "Bob Owner"


# ── Test Document Import Service MCP Integration ────────────────────────────

@pytest.mark.asyncio
async def test_import_service_routes_jira_to_mcp(mock_jira):
    # Setup mock issue
    mock_issue = MagicMock()
    mock_issue.fields.summary = "Jira Import Summary"
    mock_issue.fields.description = "Jira Import Description"
    mock_issue.fields.project.key = "PROJ"
    mock_issue.fields.reporter.displayName = "John"
    mock_issue.fields.assignee.displayName = "Jane"
    mock_issue.fields.labels = []
    mock_jira.issue.return_value = mock_issue

    service = DocumentImportService()
    extracted = await service.import_document("jira:PROJ-999")

    assert "Summary: Jira Import Summary" in extracted
    assert "Description:\nJira Import Description" in extracted


@pytest.mark.asyncio
async def test_import_service_routes_confluence_to_mcp(mock_confluence):
    # Setup mock page
    mock_page = {
        "title": "Confluence Import Title",
        "space": {"key": "DS"},
        "version": {"number": 1},
        "history": {"createdDate": "2026-07-01", "createdBy": {"displayName": "Alice"}},
        "_links": {"base": "https://test", "webui": "/1"},
        "body": {
            "storage": {
                "value": "<p>Confluence Import Content</p>"
            }
        }
    }
    mock_confluence.get_page_by_id.return_value = mock_page

    service = DocumentImportService()
    extracted = await service.import_document("confluence:888")

    assert "Confluence Import Content" in extracted
