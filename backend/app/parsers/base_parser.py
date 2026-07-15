from __future__ import annotations

from abc import ABC, abstractmethod


class BaseParser(ABC):
    """Abstract contract for document parsers."""

    @abstractmethod
    async def parse(self, file_path: str) -> str:
        """Extract and return the document text as a string."""
