from __future__ import annotations

from pathlib import Path

from app.parsers.base_parser import BaseParser
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TXTParser(BaseParser):
    """Parser implementation for plain text documents."""

    async def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        logger.info("Parsing TXT document: %s", file_path)
        return path.read_text(encoding="utf-8").strip()
