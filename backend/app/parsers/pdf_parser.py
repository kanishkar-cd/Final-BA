from __future__ import annotations

from pathlib import Path

from app.parsers.base_parser import BaseParser
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PDFParser(BaseParser):
    """Parser implementation for PDF documents."""

    async def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        logger.info("Parsing PDF document: %s", file_path)
        try:
            import pypdf
        except ImportError as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError("pypdf is required to parse PDF files") from exc

        reader = pypdf.PdfReader(str(path))
        text_parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(part for part in text_parts if part).strip()
