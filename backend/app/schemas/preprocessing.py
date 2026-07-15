from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.chunk import Chunk


@dataclass(frozen=True)
class PreprocessingPipelineResponse:
    """Output from the document preprocessing pipeline."""

    parsed_text: str
    chunks: list[Chunk]
    labeled_chunks: list[Chunk]
    requirement_analysis: Any
