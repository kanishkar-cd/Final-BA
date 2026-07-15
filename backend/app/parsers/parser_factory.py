from __future__ import annotations

from pathlib import Path
from typing import Type

from app.parsers.base_parser import BaseParser
from app.parsers.docling_parser import DoclingParser


class ParserFactory:
    """Factory for creating the appropriate parser for a document."""

    _parsers: dict[str, Type[BaseParser]] = {
        ".pdf": DoclingParser,
        ".docx": DoclingParser,
        ".txt": DoclingParser,
    }

    @classmethod
    def create(cls, file_path: str | Path) -> BaseParser:
        """Instantiate the correct parser based on the file extension."""
        extension = Path(file_path).suffix.lower()
        parser_cls = cls._parsers.get(extension)
        if parser_cls is None:
            raise ValueError(
                f"Unsupported file type: {extension}. Supported types are: {sorted(cls._parsers)}"
            )
        return parser_cls()
