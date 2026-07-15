from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence
from uuid import UUID, uuid4

from app.config.settings import SemanticChunkingSettings, settings
from app.schemas import Chunk


class SentenceEmbeddingModel(Protocol):
    """Minimal interface needed from sentence-transformer style models."""

    def encode(self, sentences: Sequence[str]) -> Any:
        """Return one embedding vector per input sentence."""


class SentenceTransformerEmbeddingModel:
    """Lazy wrapper around sentence-transformers for production semantic chunking."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any | None = None

    def encode(self, sentences: Sequence[str]) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - runtime dependency guard
                raise RuntimeError(
                    "sentence-transformers is required for semantic chunking"
                ) from exc

            self._model = SentenceTransformer(self.model_name)

        return self._model.encode(list(sentences))


@dataclass(frozen=True)
class SentenceUnit:
    """A normalized sentence with its token estimate."""

    text: str
    token_count: int


class ChunkService:
    """Create semantic chunks from parsed document text."""

    DEFAULT_MAX_TOKENS = settings.semantic_chunking.maximum_chunk_tokens

    _sentence_pattern = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
    _token_pattern = re.compile(r"\w+(?:[-']\w+)*|[^\w\s]", re.UNICODE)

    def __init__(
        self,
        max_tokens: int | None = None,
        *,
        embedding_model: SentenceEmbeddingModel | None = None,
        model_name: str | None = None,
        similarity_threshold: float | None = None,
        min_tokens: int | None = None,
        chunking_settings: SemanticChunkingSettings | None = None,
    ) -> None:
        config = chunking_settings or settings.semantic_chunking
        resolved_model_name = model_name or config.embedding_model_name
        resolved_similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else config.similarity_threshold
        )
        resolved_min_tokens = (
            min_tokens if min_tokens is not None else config.minimum_chunk_tokens
        )
        resolved_max_tokens = (
            max_tokens if max_tokens is not None else config.maximum_chunk_tokens
        )

        if resolved_max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        if resolved_min_tokens < 0:
            raise ValueError("min_tokens must be greater than or equal to zero")
        if resolved_min_tokens > resolved_max_tokens:
            raise ValueError("min_tokens must be less than or equal to max_tokens")
        if not -1.0 <= resolved_similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between -1.0 and 1.0")

        self.max_tokens = resolved_max_tokens
        self.min_tokens = resolved_min_tokens
        self.similarity_threshold = resolved_similarity_threshold
        self.fast_mode = os.getenv("FAST_DOCUMENT_CHUNKING", "false").lower() == "true"
        self.embedding_model = embedding_model or SentenceTransformerEmbeddingModel(
            resolved_model_name
        )

    def chunk_text(
        self,
        text: str,
        *,
        document_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
        source: str | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Split parsed document text into semantic Chunk schema objects."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        resolved_document_id = self._resolve_uuid(document_id)
        resolved_project_id = self._resolve_uuid(project_id)
        sentences = self._split_into_sentences(text)
        if not sentences:
            return []

        semantic_groups = self._group_sentences_by_similarity(sentences)
        sentence_chunks = [
            sentence_chunk
            for group in semantic_groups
            for sentence_chunk in self._merge_small_chunks(
                self._split_group_by_token_limit(group)
            )
        ]
        chunk_contents = [self._compose_chunk(chunk) for chunk in sentence_chunks]

        chunks: list[Chunk] = []
        for content in chunk_contents:
            chunk_index = len(chunks)
            metadata = {
                "sequence_number": chunk_index + 1,
                "source": source,
                "source_metadata": source_metadata or {},
            }
            chunks.append(
                Chunk.create(
                    document_id=resolved_document_id,
                    project_id=resolved_project_id,
                    chunk_index=chunk_index,
                    section_title=self._section_title_for_content(content),
                    content=content,
                    token_count=self.count_tokens(content),
                    context=None,
                    metadata=metadata,
                )
            )

        return chunks

    def deduplicate_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """
        B2.2: Collapse near-identical chunks by content hash.
        Duplicate chunks multiply embedding storage cost and retrieval noise.
        """
        seen_hashes: set[str] = set()
        deduped: list[Chunk] = []
        for chunk in chunks:
            if chunk.content_hash not in seen_hashes:
                seen_hashes.add(chunk.content_hash)
                deduped.append(chunk)
        return deduped

    def count_tokens(self, text: str) -> int:
        """Estimate token count without requiring a tokenizer runtime dependency."""
        return len(self._token_pattern.findall(text))

    def _split_into_sentences(self, text: str) -> list[SentenceUnit]:
        normalized_blocks = self._normalize_blocks(text)
        sentences: list[SentenceUnit] = []

        for block in normalized_blocks:
            for sentence in self._sentence_pattern.split(block):
                normalized_sentence = self._normalize_inline_whitespace(sentence)
                if normalized_sentence:
                    sentences.append(
                        SentenceUnit(
                            text=normalized_sentence,
                            token_count=self.count_tokens(normalized_sentence),
                        )
                    )

        return sentences

    def _group_sentences_by_similarity(
        self,
        sentences: Sequence[SentenceUnit],
    ) -> list[list[SentenceUnit]]:
        if len(sentences) <= 1:
            return [list(sentences)]
        if self.fast_mode:
            # Token-limit splitting still runs afterward. Keeping one group
            # avoids transformer startup and external model checks for local
            # interactive workflows.
            return [list(sentences)]

        embeddings = self._encode_sentences([sentence.text for sentence in sentences])
        groups: list[list[SentenceUnit]] = [[sentences[0]]]

        for index in range(1, len(sentences)):
            similarity = self._cosine_similarity(embeddings[index - 1], embeddings[index])
            if similarity >= self.similarity_threshold:
                groups[-1].append(sentences[index])
            else:
                groups.append([sentences[index]])

        return groups

    def _split_group_by_token_limit(
        self,
        group: Sequence[SentenceUnit],
    ) -> list[list[SentenceUnit]]:
        chunks: list[list[SentenceUnit]] = []
        current_sentences: list[SentenceUnit] = []
        current_tokens = 0

        for sentence in group:
            if sentence.token_count > self.max_tokens:
                if current_sentences:
                    chunks.append(current_sentences)
                    current_sentences = []
                    current_tokens = 0
                chunks.extend(self._split_oversized_sentence(sentence.text))
                continue

            if current_sentences and current_tokens + sentence.token_count > self.max_tokens:
                chunks.append(current_sentences)
                current_sentences = [sentence]
                current_tokens = sentence.token_count
            else:
                current_sentences.append(sentence)
                current_tokens += sentence.token_count

        if current_sentences:
            chunks.append(current_sentences)

        return chunks

    def _merge_small_chunks(
        self,
        chunks: Sequence[Sequence[SentenceUnit]],
    ) -> list[list[SentenceUnit]]:
        merged_chunks = [list(chunk) for chunk in chunks if chunk]
        if self.min_tokens == 0 or len(merged_chunks) <= 1:
            return merged_chunks

        index = 0
        while index < len(merged_chunks):
            current_chunk = merged_chunks[index]
            current_tokens = self._token_count_for_sentences(current_chunk)
            if current_tokens >= self.min_tokens:
                index += 1
                continue

            merge_index = self._best_adjacent_merge_index(merged_chunks, index)
            if merge_index is None:
                index += 1
                continue

            if merge_index < index:
                merged_chunks[merge_index].extend(current_chunk)
                del merged_chunks[index]
                index = max(merge_index - 1, 0)
            else:
                current_chunk.extend(merged_chunks[merge_index])
                del merged_chunks[merge_index]

        return merged_chunks

    def _best_adjacent_merge_index(
        self,
        chunks: Sequence[Sequence[SentenceUnit]],
        index: int,
    ) -> int | None:
        current_chunk = chunks[index]
        candidates: list[tuple[int, int]] = []

        for adjacent_index in (index - 1, index + 1):
            if not 0 <= adjacent_index < len(chunks):
                continue
            adjacent_chunk = chunks[adjacent_index]
            combined_tokens = self._token_count_for_sentences(current_chunk)
            combined_tokens += self._token_count_for_sentences(adjacent_chunk)
            if combined_tokens > self.max_tokens:
                continue

            # All chunks passed here came from the same semantic group, whose
            # sentence similarity was calculated in one batched model call.
            # Prefer the smaller neighbor without re-embedding every pair.
            candidates.append((self._token_count_for_sentences(adjacent_chunk), adjacent_index))

        if not candidates:
            return None

        candidates.sort(key=lambda candidate: candidate[0])
        return candidates[0][1]

    def _token_count_for_sentences(self, sentences: Sequence[SentenceUnit]) -> int:
        return sum(sentence.token_count for sentence in sentences)

    def _split_oversized_sentence(self, sentence: str) -> list[list[SentenceUnit]]:
        tokens = self._token_pattern.findall(sentence)
        chunks: list[list[SentenceUnit]] = []
        for start in range(0, len(tokens), self.max_tokens):
            chunk_text = self._untokenize(tokens[start : start + self.max_tokens])
            chunks.append(
                [
                    SentenceUnit(
                        text=chunk_text,
                        token_count=self.count_tokens(chunk_text),
                    )
                ]
            )
        return chunks

    def _encode_sentences(self, sentences: Sequence[str]) -> list[list[float]]:
        raw_embeddings = self.embedding_model.encode(sentences)
        embeddings = [self._as_float_vector(vector) for vector in raw_embeddings]

        if len(embeddings) != len(sentences):
            raise RuntimeError("embedding model returned an unexpected number of vectors")

        return embeddings

    def _as_float_vector(self, vector: Any) -> list[float]:
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        return [float(value) for value in vector]

    def _cosine_similarity(self, left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right):
            raise RuntimeError("embedding vectors must have the same dimensions")

        dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0

        return dot_product / (left_norm * right_norm)

    def _normalize_blocks(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n\s*\n+", normalized)
        return [self._normalize_inline_whitespace(block) for block in blocks if block.strip()]

    def _compose_chunk(self, sentences: Sequence[SentenceUnit]) -> str:
        return " ".join(sentence.text for sentence in sentences).strip()

    def _normalize_inline_whitespace(self, text: str) -> str:
        return " ".join(text.split()).strip()

    def _untokenize(self, tokens: Sequence[str]) -> str:
        text = " ".join(tokens)
        text = re.sub(r"\s+([,.;:!?%)\]}])", r"\1", text)
        text = re.sub(r"([({\[])\s+", r"\1", text)
        return text.strip()

    def _resolve_uuid(self, value: UUID | str | None) -> UUID:
        if value is None:
            return uuid4()
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            from uuid import uuid5, NAMESPACE_DNS
            return uuid5(NAMESPACE_DNS, str(value))

    def _section_title_for_content(self, content: str) -> str:
        first_sentence = self._sentence_pattern.split(content.strip(), maxsplit=1)[0]
        if first_sentence and not first_sentence.endswith((".", "!", "?")):
            return first_sentence[:140]
        return ""


def chunk_text(
    text: str,
    *,
    document_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
    source: str | None = None,
    source_metadata: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    embedding_model: SentenceEmbeddingModel | None = None,
    model_name: str | None = None,
    similarity_threshold: float | None = None,
    min_tokens: int | None = None,
    chunking_settings: SemanticChunkingSettings | None = None,
) -> list[Chunk]:
    """Convenience wrapper for callers that do not need to manage a service instance."""
    return ChunkService(
        max_tokens=max_tokens,
        embedding_model=embedding_model,
        model_name=model_name,
        similarity_threshold=similarity_threshold,
        min_tokens=min_tokens,
        chunking_settings=chunking_settings,
    ).chunk_text(
        text,
        document_id=document_id,
        project_id=project_id,
        source=source,
        source_metadata=source_metadata,
    )
