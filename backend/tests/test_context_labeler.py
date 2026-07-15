from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.labeling.context_labeler import ContextLabeler, ContextLabelingError
from app.schemas import Chunk


DOCUMENT_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


class FakeLLMExecutor:
    def __init__(self, labels: dict[str, str]) -> None:
        self.labels = labels
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        prompt: str,
        model_name: str,
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "model_name": model_name,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
            }
        )
        chunk_payload = prompt.split("Chunks:", maxsplit=1)[1].strip()
        chunk_ids = [chunk["chunk_id"] for chunk in json.loads(chunk_payload)]
        return json.dumps(
            {
                "labels": [
                    {"chunk_id": chunk_id, "context": self.labels[chunk_id]}
                    for chunk_id in chunk_ids
                ]
            }
        )


def make_chunk(chunk_id: str, content: str, sequence: int) -> Chunk:
    return Chunk.create(
        document_id=DOCUMENT_ID,
        project_id=PROJECT_ID,
        chunk_index=sequence - 1,
        content=content,
        token_count=len(content.split()),
        context=None,
        metadata={"sequence_number": sequence, "source": "sample.txt"},
    )


def test_labels_chunks_in_a_single_batch_and_preserves_fields() -> None:
    chunks = [
        make_chunk("chunk-1", "Users can sign in using OTP.", 1),
        make_chunk("chunk-2", "Payments are reconciled nightly.", 2),
    ]
    executor = FakeLLMExecutor(
        {
            str(chunks[0].id): "Authentication",
            str(chunks[1].id): "Payment",
        }
    )
    labeler = ContextLabeler(
        llm_executor=executor,
        batch_size=10,
        model_name="test-model",
        max_tokens=200,
    )

    labeled_chunks = asyncio.run(labeler.label_chunks(chunks))

    assert len(executor.calls) == 1
    assert [chunk.context for chunk in labeled_chunks] == ["Authentication", "Payment"]
    assert labeled_chunks[0].id == chunks[0].id
    assert labeled_chunks[0].document_id == chunks[0].document_id
    assert labeled_chunks[0].project_id == chunks[0].project_id
    assert labeled_chunks[0].content == chunks[0].content
    assert labeled_chunks[0].token_count == chunks[0].token_count
    assert labeled_chunks[0].metadata == chunks[0].metadata
    assert chunks[0].context is None
    assert executor.calls[0]["model_name"] == "test-model"
    assert executor.calls[0]["max_tokens"] == 200


def test_batches_large_chunk_lists_without_calling_llm_per_chunk() -> None:
    chunks = [
        make_chunk(f"chunk-{index}", f"Chunk content {index}.", index)
        for index in range(1, 6)
    ]
    executor = FakeLLMExecutor(
        {str(chunk.id): "Administration" for chunk in chunks}
    )
    labeler = ContextLabeler(
        llm_executor=executor,
        batch_size=2,
        model_name="test-model",
    )

    labeled_chunks = asyncio.run(labeler.label_chunks(chunks))

    assert len(executor.calls) == 3
    assert len(executor.calls) < len(chunks)
    assert all(chunk.context == "Administration" for chunk in labeled_chunks)


def test_rejects_invalid_llm_json() -> None:
    async def invalid_executor(**_: Any) -> str:
        return "not json"

    labeler = ContextLabeler(llm_executor=invalid_executor, model_name="test-model")

    try:
        asyncio.run(labeler.label_chunks([make_chunk("chunk-1", "Content.", 1)]))
    except ContextLabelingError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("Expected ContextLabelingError")


def test_retries_truncated_json_with_smaller_batches() -> None:
    calls = 0

    async def truncating_executor(*, prompt: str, **_: Any) -> str:
        nonlocal calls
        calls += 1
        chunk_payload = prompt.split("Chunks:", maxsplit=1)[1].strip()
        chunk_ids = [chunk["chunk_id"] for chunk in json.loads(chunk_payload)]
        if len(chunk_ids) > 1:
            return '{"labels":[{"chunk_id":"truncated'
        return json.dumps(
            {"labels": [{"chunk_id": chunk_ids[0], "context": "Recovered"}]}
        )

    chunks = [
        make_chunk("chunk-1", "First requirement.", 1),
        make_chunk("chunk-2", "Second requirement.", 2),
    ]
    labeler = ContextLabeler(
        llm_executor=truncating_executor,
        batch_size=8,
        model_name="test-model",
    )

    labeled_chunks = asyncio.run(labeler.label_chunks(chunks))

    assert calls == 3
    assert [chunk.context for chunk in labeled_chunks] == ["Recovered", "Recovered"]


def test_requires_a_label_for_every_chunk() -> None:
    async def missing_label_executor(**_: Any) -> str:
        return json.dumps({"labels": []})

    labeler = ContextLabeler(
        llm_executor=missing_label_executor,
        model_name="test-model",
    )

    try:
        asyncio.run(labeler.label_chunks([make_chunk("chunk-1", "Content.", 1)]))
    except ContextLabelingError as exc:
        assert "every chunk" in str(exc)
    else:
        raise AssertionError("Expected ContextLabelingError")


def test_provider_failure_uses_local_labels_instead_of_aborting() -> None:
    async def failed_provider(**_: Any) -> str:
        raise ContextLabelingError("Context labeling failed while invoking the LLM.")

    previous_fallback = os.environ.get("CONTEXT_LABELING_FALLBACK_MODEL")
    os.environ["CONTEXT_LABELING_FALLBACK_MODEL"] = ""
    try:
        chunk = make_chunk("chunk-1", "Users authenticate with an OTP.", 1)
        labeler = ContextLabeler(llm_executor=failed_provider, model_name="test-model")

        labeled_chunks = asyncio.run(labeler.label_chunks([chunk]))

        assert labeled_chunks[0].context == "Users authenticate with"
    finally:
        if previous_fallback is None:
            os.environ.pop("CONTEXT_LABELING_FALLBACK_MODEL", None)
        else:
            os.environ["CONTEXT_LABELING_FALLBACK_MODEL"] = previous_fallback
