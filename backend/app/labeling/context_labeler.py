from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from json import JSONDecodeError
from typing import Any, Protocol, Sequence

from app.config.settings import settings
from app.prompts.prompt_manager import PromptManager
from app.schemas import Chunk
from app.shared.llm_client import LLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ContextLabelingError(Exception):
    """Raised when context labeling fails."""


class ContextLabelingExecutor(Protocol):
    """Async LLM executor used by ContextLabeler."""

    async def __call__(
        self,
        *,
        prompt: str,
        model_name: str,
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> Any:
        """Return an LLM response for a batch context-labeling prompt."""


class ContextLabeler:
    """Assign concise business context labels to semantic chunks in batches."""

    def __init__(
        self,
        *,
        prompt_manager: PromptManager | None = None,
        llm_executor: ContextLabelingExecutor | None = None,
        batch_size: int | None = None,
        model_name: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        resolved_batch_size = batch_size or settings.context_labeling_batch_size
        if resolved_batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        self.prompt_manager = prompt_manager or PromptManager()
        self.llm_service = LLMService(self.prompt_manager)
        self.llm_executor = llm_executor or self._default_llm_executor
        self.batch_size = resolved_batch_size
        self.model_name = model_name
        self.max_tokens = (
            max_tokens
            if max_tokens is not None
            else settings.context_labeling_max_tokens
        )

    async def label_chunks(self, chunks: Sequence[Chunk]) -> list[Chunk]:
        """Return chunks with only their context field updated."""
        if not chunks:
            return []

        updated_chunks: list[Chunk] = []
        for batch in self._batched(chunks, self.batch_size):
            try:
                labels = await self._label_batch(batch)
            except ContextLabelingError as primary_error:
                if "invoking the LLM" not in str(primary_error):
                    raise
                labels = await self._fallback_labels(batch, primary_error)
            updated_chunks.extend(self._apply_labels(batch, labels))

        return updated_chunks

    async def _fallback_labels(
        self,
        chunks: Sequence[Chunk],
        primary_error: Exception,
    ) -> dict[str, str]:
        """Use a second provider, then local labels, instead of aborting ingestion."""
        fallback_model = os.getenv("CONTEXT_LABELING_FALLBACK_MODEL", "llama3.1-8b").strip()
        if fallback_model and fallback_model != self.model_name:
            logger.warning(
                "Primary context labeling failed (%s); trying fallback model '%s'.",
                primary_error,
                fallback_model,
            )
            try:
                payload = self._serialize_chunks(chunks)
                response = await self._default_llm_executor(
                    prompt=self.prompt_manager.get_context_labeling_prompt(payload),
                    model_name=fallback_model,
                    system_prompt=self.prompt_manager.get_context_labeling_system_prompt(),
                    max_tokens=self.max_tokens,
                )
                return self._parse_labels(self._response_content(response), chunks)
            except Exception as fallback_error:
                logger.warning(
                    "Fallback context labeling failed (%s); using local labels.",
                    fallback_error,
                )

        return {str(chunk.id): self._local_context_label(chunk) for chunk in chunks}

    def _local_context_label(self, chunk: Chunk) -> str:
        """Produce a stable label without an external model call."""
        section = (chunk.section_title or "").strip()
        if section and section.lower() not in {"unknown", "untitled", "document"}:
            return self._normalize_context(section)

        words = re.findall(r"[A-Za-z0-9]+", " ".join(chunk.content.split()))
        return self._normalize_context(" ".join(words[:3]) or "General requirement")

    async def _label_batch(self, chunks: Sequence[Chunk]) -> dict[str, str]:
        payload = self._serialize_chunks(chunks)
        prompt = self.prompt_manager.get_context_labeling_prompt(payload)
        model_name = self.model_name or self.prompt_manager.get_default_model()
        system_prompt = self.prompt_manager.get_context_labeling_system_prompt()

        try:
            response = await self.llm_executor(
                prompt=prompt,
                model_name=model_name,
                system_prompt=system_prompt,
                max_tokens=self.max_tokens,
            )
            raw_content = self._response_content(response)
            try:
                return self._parse_labels(raw_content, chunks)
            except ContextLabelingError as exc:
                if "invalid JSON" not in str(exc) or len(chunks) <= 1:
                    raise
                midpoint = len(chunks) // 2
                logger.warning(
                    "Context-label JSON was truncated for %d chunks; retrying as %d and %d chunks.",
                    len(chunks),
                    midpoint,
                    len(chunks) - midpoint,
                )
                first = await self._label_batch(chunks[:midpoint])
                second = await self._label_batch(chunks[midpoint:])
                return {**first, **second}
        except ContextLabelingError:
            raise
        except Exception as exc:
            logger.error("Context labeling failed: %s", exc, exc_info=True)
            raise ContextLabelingError("Context labeling failed.") from exc

    async def _default_llm_executor(
        self,
        *,
        prompt: str,
        model_name: str,
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> Any:
        try:
            from app.shared.llm_client import LLMServiceError
            return await self.llm_service.execute(
                prompt=prompt,
                model_name=model_name,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                reasoning_effort="low",
            )
        except LLMServiceError as exc:
            raise ContextLabelingError(
                "Context labeling failed while invoking the LLM."
            ) from exc

    def _parse_labels(
        self,
        raw_content: str,
        chunks: Sequence[Chunk],
    ) -> dict[str, str]:
        try:
            payload = json.loads(self._strip_markdown_fences(raw_content))
        except JSONDecodeError as exc:
            raise ContextLabelingError("Context labeling returned invalid JSON.") from exc

        labels = payload.get("labels") if isinstance(payload, dict) else None
        if not isinstance(labels, list):
            raise ContextLabelingError("Context labeling response is missing labels.")

        parsed_labels: dict[str, str] = {}
        for item in labels:
            if not isinstance(item, dict):
                raise ContextLabelingError("Context labeling response is malformed.")

            chunk_id = item.get("chunk_id")
            context = item.get("context")
            if not isinstance(chunk_id, str) or not isinstance(context, str):
                raise ContextLabelingError("Context labeling response is malformed.")

            parsed_labels[chunk_id] = self._normalize_context(context)

        expected_ids = {str(chunk.id) for chunk in chunks}
        missing_ids = expected_ids - parsed_labels.keys()
        if missing_ids:
            raise ContextLabelingError(
                "Context labeling response did not include every chunk."
            )

        return parsed_labels

    def _apply_labels(
        self,
        chunks: Sequence[Chunk],
        labels: dict[str, str],
    ) -> list[Chunk]:
        return [replace(chunk, context=labels[str(chunk.id)]) for chunk in chunks]

    def _serialize_chunks(self, chunks: Sequence[Chunk]) -> str:
        payload = [
            {
                "chunk_id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "section_title": chunk.section_title,
                "content": chunk.content,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def _normalize_context(self, context: str) -> str:
        words = context.replace("_", " ").replace("-", " ").split()
        normalized = " ".join(words[:3]).strip()
        if not normalized:
            raise ContextLabelingError("Context labeling returned an empty context.")
        return normalized

    def _response_content(self, response: Any) -> str:
        if isinstance(response, str):
            return response

        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content

        raise ContextLabelingError("Context labeling response has no text content.")

    def _strip_markdown_fences(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            first_newline = stripped.find("\n")
            if first_newline != -1:
                stripped = stripped[first_newline + 1 :]
            if stripped.endswith("```"):
                stripped = stripped[:-3]
            stripped = stripped.strip()
        return stripped

    def _batched(self, chunks: Sequence[Chunk], batch_size: int) -> list[Sequence[Chunk]]:
        return [
            chunks[start : start + batch_size]
            for start in range(0, len(chunks), batch_size)
        ]
