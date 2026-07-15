from __future__ import annotations

from pathlib import Path

from app.parsers.base_parser import BaseParser
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DOCXParser(BaseParser):
    """Parser implementation for DOCX documents."""

    async def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        logger.info("Parsing DOCX document: %s", file_path)
        try:
            from docx import Document
        except ImportError as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError("python-docx is required to parse DOCX files") from exc

        document = Document(str(path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        return "\n".join(paragraphs).strip()
