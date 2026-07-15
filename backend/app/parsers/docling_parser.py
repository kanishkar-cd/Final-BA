from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from app.parsers.base_parser import BaseParser
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DoclingParser(BaseParser):
    """Parser implementation that uses Docling as the primary document engine."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

    def __init__(self, converter_factory: Callable[[], Any] | None = None) -> None:
        self._converter_factory = converter_factory or self._create_converter

    async def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {extension}. Supported types are: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        if extension == ".txt":
            logger.info("Reading TXT content directly: %s", path)
            return path.read_text(encoding="utf-8").strip()

        logger.info("Parsing document with Docling: %s", path)
        try:
            extracted_text = await asyncio.to_thread(self._parse_with_docling, str(path))
        except Exception as exc:  # pragma: no cover - logging wrapper
            logger.exception("Docling failed to parse document: %s", path)
            raise RuntimeError(f"Docling failed to parse document: {path}") from exc

        return extracted_text.strip() if extracted_text else ""

    def _parse_with_docling(self, file_path: str) -> str:
        converter = self._converter_factory()
        result = self._convert_document(converter, file_path)
        return self._extract_text(result)

    def _create_converter(self) -> Any:
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        except ImportError as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError("Docling is required to parse documents") from exc

        # Disable heavy deep learning layout and OCR models to prevent memory exhaustion (std::bad_alloc)
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.do_table_structure = False

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=PyPdfiumDocumentBackend
                )
            }
        )

    def _convert_document(self, converter: Any, file_path: str) -> Any:
        convert = getattr(converter, "convert", None)
        if not callable(convert):
            raise RuntimeError("Docling converter does not expose a usable convert() method")

        try:
            return convert(file_path)
        except TypeError:
            return convert(input=file_path)

    def _extract_text(self, result: Any) -> str:
        if result is None:
            return ""

        document = getattr(result, "document", None)
        if document is not None:
            text = self._extract_text(document)
            if text:
                return text

        export_to_text = getattr(result, "export_to_text", None)
        if callable(export_to_text):
            exported_text = export_to_text()
            if isinstance(exported_text, str) and exported_text.strip():
                return exported_text

        export_to_markdown = getattr(result, "export_to_markdown", None)
        if callable(export_to_markdown):
            exported_markdown = export_to_markdown()
            if isinstance(exported_markdown, str) and exported_markdown.strip():
                return exported_markdown

        text_attr = getattr(result, "text", None)
        if isinstance(text_attr, str) and text_attr.strip():
            return text_attr

        markdown_attr = getattr(result, "markdown", None)
        if isinstance(markdown_attr, str) and markdown_attr.strip():
            return markdown_attr

        return ""
