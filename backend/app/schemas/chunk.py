from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Chunk:
    """Database-facing document chunk entity."""

    id: UUID
    document_id: UUID
    project_id: UUID
    chunk_index: int
    section_title: str
    context: str | None
    content: str
    token_count: int
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if self.chunk_index < 0:
            raise ValueError("chunk_index must be non-negative")
        if self.token_count < 0:
            raise ValueError("token_count must be non-negative")
        if len(self.content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.content_hash
        ):
            raise ValueError("content_hash must be a SHA-256 hex digest")

    @classmethod
    def create(
        cls,
        *,
        content: str,
        token_count: int,
        document_id: UUID,
        project_id: UUID,
        chunk_index: int,
        section_title: str = "",
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Chunk":
        from hashlib import sha256

        return cls(
            id=uuid4(),
            document_id=document_id,
            project_id=project_id,
            chunk_index=chunk_index,
            section_title=section_title,
            context=context,
            content=content,
            token_count=token_count,
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
            metadata=metadata or {},
        )
