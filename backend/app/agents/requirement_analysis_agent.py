"""
Agent one: requirement analysis and extraction.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# pyrefly: ignore [missing-import]
from designlab_core.utilities.logger import get_logger

from app.agents.base_agent import BaseAgent
from app.agents.exceptions import RequirementAnalysisAgentError
from app.prompts.prompt_manager import PromptManager
from app.shared.llm_client import LLMService, LLMServiceError


_logger = get_logger("agents.requirement_analysis")


# pyrefly: ignore [parse-error]
class RequirementAnalysisOutput(BaseModel):
    """
    Structured output produced by the requirement analysis agent.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "actors": ["Customer"],
                "functional_requirements": [
                    "Customers can log in using email and OTP.",
                    "The system shall lock the account after 5 failed attempts.",
                ],
                "non_functional_requirements": ["Security"],
                "dependencies": ["OTP Service"],
                "business_goals": ["Increase security."],
                "edge_cases": ["Account locks after 5 failed OTP attempts."],
                "constraints": ["OTP must expire within the configured time limit."],
            }
        }
    )

    actors: list[str] = Field(default_factory=list)
    functional_requirements: list[str] = Field(default_factory=list)
    non_functional_requirements: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    business_goals: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class RequirementAnalysisAgent(BaseAgent):
    """
    Extract actors, requirements, dependencies, goals, edge cases, and constraints.
    """

    output_schema = RequirementAnalysisOutput

    def __init__(
        self,
        prompt_manager: PromptManager | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self.prompt_manager = prompt_manager or PromptManager()
        self.llm_service = llm_service or LLMService(self.prompt_manager)

    async def run(
        self,
        chunks: list[dict[str, Any]] | str,
        *,
        model_name: str | None = None,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> RequirementAnalysisOutput:
        """
        Analyze requirement chunks and return validated structured JSON.
        """

        try:
            system_prompt_str = (
                system_prompt
                or self.prompt_manager.get_requirement_analysis_system_prompt()
            )
            max_input_chars = int(
                os.getenv("REQUIREMENT_ANALYSIS_MAX_INPUT_CHARS", "18000")
            )
            batches = self._batch_chunks(chunks, max_input_chars=max_input_chars)
            outputs = [
                await self._analyze_batch(
                    batch,
                    system_prompt=system_prompt_str,
                    model_name=model_name,
                    max_tokens=max_tokens,
                )
                for batch in batches
            ]
            return self._merge_outputs(outputs)

        except (ValidationError, json.JSONDecodeError) as exc:
            _logger.error(
                "Requirement analysis response validation failed: %s",
                exc,
                exc_info=True,
            )
            raise RequirementAnalysisAgentError(
                "Requirement analysis returned invalid JSON or schema-incompatible output."
            ) from exc

        except LLMServiceError as exc:
            _logger.error("Requirement analysis LLM call failed: %s", exc, exc_info=True)
            raise RequirementAnalysisAgentError(
                "Requirement analysis failed while invoking the LLM."
            ) from exc

        except Exception as exc:
            _logger.error("Unexpected requirement analysis failure: %s", exc, exc_info=True)
            raise RequirementAnalysisAgentError(
                "Requirement analysis failed due to an unexpected backend error."
            ) from exc

    async def _analyze_batch(
        self,
        chunks: list[dict[str, Any]] | str,
        *,
        system_prompt: str,
        model_name: str | None,
        max_tokens: int | None,
    ) -> RequirementAnalysisOutput:
        serialized_chunks = self._serialize_chunks(chunks)
        prompt = self.prompt_manager.get_requirement_analysis_prompt(serialized_chunks)
        return await self.llm_service.execute(
            prompt=prompt,
            system_prompt=system_prompt,
            response_schema=self.output_schema,
            max_tokens=max_tokens,
            model_name=model_name,
        )

    @classmethod
    def _batch_chunks(
        cls,
        chunks: list[dict[str, Any]] | str,
        *,
        max_input_chars: int,
    ) -> list[list[dict[str, Any]] | str]:
        if max_input_chars <= 0:
            raise ValueError("REQUIREMENT_ANALYSIS_MAX_INPUT_CHARS must be positive")
        if isinstance(chunks, str):
            return [
                chunks[index:index + max_input_chars]
                for index in range(0, len(chunks), max_input_chars)
            ] or [""]

        batches: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_size = 2  # JSON list brackets
        for chunk in chunks:
            chunk_size = len(json.dumps(chunk, ensure_ascii=False)) + 2
            if current and current_size + chunk_size > max_input_chars:
                batches.append(current)
                current = []
                current_size = 2
            current.append(chunk)
            current_size += chunk_size
        if current or not batches:
            batches.append(current)
        return batches

    @classmethod
    def _merge_outputs(
        cls,
        outputs: list[RequirementAnalysisOutput],
    ) -> RequirementAnalysisOutput:
        merged: dict[str, list[str]] = {}
        for field_name in cls.output_schema.model_fields:
            values = [
                item
                for output in outputs
                for item in getattr(output, field_name)
            ]
            unique_values: list[str] = []
            seen: set[str] = set()
            for value in values:
                normalized = " ".join(value.casefold().split()).rstrip(".")
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    unique_values.append(value.strip())
            merged[field_name] = unique_values
        return cls.output_schema(**merged)

    @staticmethod
    def _serialize_chunks(chunks: list[dict[str, Any]] | str) -> str:
        if isinstance(chunks, str):
            return chunks
        return json.dumps(chunks, ensure_ascii=False, indent=2)

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            first_newline = stripped.find("\n")
            if first_newline != -1:
                stripped = stripped[first_newline + 1:]
            if stripped.endswith("```"):
                stripped = stripped[:-3]
            stripped = stripped.strip()
        return stripped
