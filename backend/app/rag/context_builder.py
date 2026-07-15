"""
Context Builder.

Converts the top reranked chunks into an LLM-ready context package
consumed by Agent 3 (Story Generation) and Agent 4 (Validation).

Output contract
---------------
    {
        "epic": "Authentication",
        "feature": "Login",
        "source_chunks": [...],          # RetrievedChunkResult list
        "supporting_requirements": [...], # requirement codes found in chunks
        "dependencies": [...],            # dependency strings extracted from metadata
        "business_rules": [...],          # business-rule strings extracted from metadata
        "retrieval_metadata": {...}       # provenance / observability
    }

Traceability is preserved through:
  - chunk_id on every source chunk
  - document_id on every source chunk
  - source field (bm25 / dense / rrf / reranked / rrf_fallback)
  - rrf_rank / reranker_score stored in chunk.metadata

Business rules and dependencies are pulled from:
  1. Chunk metadata keys ``business_rules`` and ``dependencies``
  2. Content heuristics (lines starting with "BR-", "DEP-", "Rule:")
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.schemas.rag import (
    ContextPackage,
    RetrievedChunkResult,
    SupportingRequirement,
    TraceabilityResponse,
)

logger = logging.getLogger("rag.context_builder")

# Regex patterns for heuristic extraction from chunk content
_REQUIREMENT_PATTERN = re.compile(r"\b(FR|NFR|BR|REQ|AC|UC)-\d+\b", re.IGNORECASE)
_DEPENDENCY_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:DEP-\d+[:\s]|depends? on[:\s]|dependency[:\s])(.+)",
    re.IGNORECASE,
)
_BUSINESS_RULE_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:BR-\d+[:\s]|business rule[:\s]|rule[:\s])(.+)",
    re.IGNORECASE,
)


class ContextBuilder:
    """
    Assemble a structured LLM context package from reranked retrieval results.

    This class is intentionally stateless so it can be shared across requests.
    """

    # ------------------------------------------------------------------ #
    # Agent 3 context package
    # ------------------------------------------------------------------ #

    def build_context_package(
        self,
        *,
        epic: str,
        feature: str,
        reranked_chunks: list[RetrievedChunkResult],
        requirement_ids: list[str] | None = None,
        retrieval_metadata: dict[str, Any] | None = None,
    ) -> ContextPackage:
        """
        Build the LLM-ready context package for Agent 3.

        Parameters
        ----------
        epic:
            Epic title from Agent 2.
        feature:
            Feature title from Agent 2.
        reranked_chunks:
            Top chunks from the reranker (already scored and ranked).
        requirement_ids:
            Explicit requirement codes from Agent 2 output.
        retrieval_metadata:
            Latency / provenance dict to embed in the package.

        Returns
        -------
        ContextPackage
        """
        t0 = time.perf_counter()

        # Gather all requirement codes: explicit + extracted from chunk content
        all_req_ids: set[str] = set(requirement_ids or [])
        for chunk in reranked_chunks:
            all_req_ids.update(self._extract_requirement_ids(chunk.content))

        supporting_requirements = self._build_supporting_requirements(
            all_req_ids, reranked_chunks
        )
        dependencies = self._collect_list_field(reranked_chunks, "dependencies")
        business_rules = self._collect_list_field(reranked_chunks, "business_rules")

        # Also extract heuristically from content
        for chunk in reranked_chunks:
            dependencies.extend(self._extract_with_pattern(_DEPENDENCY_PATTERN, chunk.content))
            business_rules.extend(self._extract_with_pattern(_BUSINESS_RULE_PATTERN, chunk.content))

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "ContextBuilder assembled package for epic='%s' feature='%s': "
            "%d chunks, %d requirements, %d deps, %d rules (%.2f ms).",
            epic[:40],
            feature[:40],
            len(reranked_chunks),
            len(supporting_requirements),
            len(dependencies),
            len(business_rules),
            elapsed_ms,
        )

        meta = dict(retrieval_metadata or {})
        meta["context_builder_latency_ms"] = elapsed_ms
        meta["chunk_ids"] = [c.chunk_id for c in reranked_chunks]
        meta["document_ids"] = list({c.document_id for c in reranked_chunks})

        return ContextPackage(
            epic=epic,
            feature=feature,
            source_chunks=reranked_chunks,
            supporting_requirements=supporting_requirements,
            dependencies=_deduplicate(dependencies),
            business_rules=_deduplicate(business_rules),
            retrieval_metadata=meta,
        )

    # ------------------------------------------------------------------ #
    # Agent 4 traceability package
    # ------------------------------------------------------------------ #

    def build_traceability_package(
        self,
        *,
        story_id: str,
        reranked_chunks: list[RetrievedChunkResult],
        requirement_ids: list[str] | None = None,
        retrieval_latency_ms: float = 0.0,
    ) -> TraceabilityResponse:
        """
        Build the grounding package for Agent 4 validation.

        Parameters
        ----------
        story_id:
            The user story being validated (e.g. "US-001").
        reranked_chunks:
            Source chunks retrieved for this story.
        requirement_ids:
            Requirement codes the story claims to address.
        retrieval_latency_ms:
            Total retrieval time for observability.

        Returns
        -------
        TraceabilityResponse
        """
        all_req_ids: set[str] = set(requirement_ids or [])
        for chunk in reranked_chunks:
            all_req_ids.update(self._extract_requirement_ids(chunk.content))

        source_requirements = self._build_supporting_requirements(
            all_req_ids, reranked_chunks
        )
        dependencies = self._collect_list_field(reranked_chunks, "dependencies")
        business_rules = self._collect_list_field(reranked_chunks, "business_rules")

        for chunk in reranked_chunks:
            dependencies.extend(self._extract_with_pattern(_DEPENDENCY_PATTERN, chunk.content))
            business_rules.extend(self._extract_with_pattern(_BUSINESS_RULE_PATTERN, chunk.content))

        logger.info(
            "TraceabilityPackage for story_id=%s: %d chunks, %d reqs.",
            story_id,
            len(reranked_chunks),
            len(source_requirements),
        )

        return TraceabilityResponse(
            story_id=story_id,
            source_chunks=reranked_chunks,
            source_requirements=source_requirements,
            dependencies=_deduplicate(dependencies),
            business_rules=_deduplicate(business_rules),
            retrieval_latency_ms=retrieval_latency_ms,
        )

    # ------------------------------------------------------------------ #
    # Extraction helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_requirement_ids(text: str) -> list[str]:
        """Extract requirement codes like FR-001, NFR-002 from text."""
        return [m.upper() for m in _REQUIREMENT_PATTERN.findall(text)]

    def _build_supporting_requirements(
        self,
        req_ids: set[str],
        chunks: list[RetrievedChunkResult],
    ) -> list[SupportingRequirement]:
        """
        Build SupportingRequirement objects.

        For each req_id we try to find the chunk that best describes it
        (the first chunk whose content contains the req_id string).
        """
        result: list[SupportingRequirement] = []
        used: set[str] = set()
        for req_id in sorted(req_ids):
            if req_id in used:
                continue
            used.add(req_id)
            description = self._find_description_for_req(req_id, chunks)
            result.append(
                SupportingRequirement(
                    id=req_id,
                    description=description,
                    source=self._find_source_for_req(req_id, chunks),
                )
            )
        return result

    @staticmethod
    def _find_description_for_req(
        req_id: str, chunks: list[RetrievedChunkResult]
    ) -> str:
        """Return the first sentence of the chunk that mentions this req_id."""
        for chunk in chunks:
            if req_id.lower() in chunk.content.lower():
                first_sentence = chunk.content.split(".")[0].strip()
                return first_sentence[:300]
        return req_id

    @staticmethod
    def _find_source_for_req(
        req_id: str, chunks: list[RetrievedChunkResult]
    ) -> str | None:
        for chunk in chunks:
            if req_id.lower() in chunk.content.lower():
                return chunk.chunk_id
        return None

    @staticmethod
    def _collect_list_field(
        chunks: list[RetrievedChunkResult], field: str
    ) -> list[str]:
        """
        Collect string values stored under *field* in chunk metadata.

        Handles both ``list[str]`` and ``str`` metadata values.
        """
        collected: list[str] = []
        for chunk in chunks:
            value = chunk.metadata.get(field)
            if isinstance(value, list):
                collected.extend(str(v) for v in value if v)
            elif isinstance(value, str) and value:
                collected.append(value)
        return collected

    @staticmethod
    def _extract_with_pattern(pattern: re.Pattern, text: str) -> list[str]:
        """Extract and clean matches for a regex pattern from text."""
        return [m.strip() for m in pattern.findall(text) if m.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _deduplicate(items: list[str]) -> list[str]:
    """Return *items* with duplicates removed, preserving insertion order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalised = item.strip()
        if normalised and normalised not in seen:
            seen.add(normalised)
            result.append(normalised)
    return result
