from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers.parser_factory import ParserFactory
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.services.import_service import DocumentImportService


@pytest.mark.parametrize(
    ("filename", "parser_type"),
    [
        ("requirements.pdf", PDFParser),
        ("requirements.docx", DOCXParser),
        ("requirements.txt", TXTParser),
    ],
)
def test_parser_factory_uses_format_specific_parser(
    filename: str,
    parser_type: type,
) -> None:
    assert isinstance(ParserFactory.create(filename), parser_type)


@pytest.mark.asyncio
async def test_txt_parser_extracts_plain_text(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Hello from the parser layer.", encoding="utf-8")

    parser = ParserFactory.create(str(file_path))
    extracted_text = await parser.parse(str(file_path))

    assert extracted_text == "Hello from the parser layer."


@pytest.mark.asyncio
async def test_import_service_returns_extracted_text(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Imported text", encoding="utf-8")

    service = DocumentImportService()
    extracted_text = await service.import_document(str(file_path))

    assert extracted_text == "Imported text"


@pytest.mark.asyncio
async def test_import_service_rejects_unsupported_extension(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.md"
    file_path.write_text("Unsupported", encoding="utf-8")

    service = DocumentImportService()

    with pytest.raises(ValueError):
        await service.import_document(str(file_path))


@pytest.mark.asyncio
async def test_import_service_onedrive_integration(monkeypatch) -> None:
    service = DocumentImportService()
    
    async def mock_download(url: str):
        assert url == "https://1drv.ms/w/s!mock-link"
        return b"Sample OneDrive Content", "test_file.txt", ".txt"
        
    monkeypatch.setattr(service, "_download_onedrive_file", mock_download)
    
    extracted_text = await service.import_document("onedrive:https://1drv.ms/w/s!mock-link")
    assert extracted_text == "Sample OneDrive Content"


@pytest.mark.asyncio
async def test_import_service_onedrive_auth_failure(monkeypatch) -> None:
    service = DocumentImportService()
    
    class MockResponse:
        def __init__(self, url, status_code, headers, content):
            self.url = url
            self.status_code = status_code
            self.headers = headers
            self.content = content
            
    async def mock_head(*args, **kwargs):
        class MockHeadResponse:
            url = "https://login.microsoftonline.com/oauth2/v2.0/authorize"
        return MockHeadResponse()
        
    async def mock_get(*args, **kwargs):
        return MockResponse(
            url="https://login.microsoftonline.com/oauth2/v2.0/authorize",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<html>Login Page</html>"
        )
        
    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def head(self, url, *args, **kwargs):
            return await mock_head()
        async def get(self, url, *args, **kwargs):
            return await mock_get()
            
    monkeypatch.setattr("httpx.AsyncClient", lambda *args, **kwargs: MockAsyncClient())
    
    with pytest.raises(PermissionError) as exc_info:
        await service._download_onedrive_file("https://1drv.ms/w/s!mock-link")
        
    assert "requires organizational authentication" in str(exc_info.value)
