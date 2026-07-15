"""
Agent Two: Epic Generation Agent.

Generates high-level Agile Epics from validated requirements.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# pyrefly: ignore [missing-import]
from designlab_core.utilities.logger import get_logger

from app.agents.base_agent import BaseAgent
from app.agents.exceptions import EpicGenerationAgentError
from app.prompts.prompt_manager import PromptManager
from app.shared.llm_client import LLMService, LLMServiceError


_logger = get_logger("agents.epic_generation")

# ==========================================================
# Individual Epic Model
# ==========================================================

class Epic(BaseModel):
    """
    Represents a single Agile Epic.
    """

    epic_id: str = Field(
        description="Unique Epic Identifier."
    )

    title: str = Field(
        description="Business-oriented Epic title."
    )

    features: list[str] = Field(
        default_factory=list,
        description="High-level features included in this Epic."
    )

    one_line_story: str = Field(
        description="One representative Agile user story for the Epic."
    )

    dependencies: list[str] = Field(
        default_factory=list,
        description="External or internal dependencies."
    )

    priority: str = Field(
        description="Priority (Critical, High, Medium, Low)."
    )


# ==========================================================
# Agent Output
# ==========================================================

class EpicGenerationOutput(BaseModel):
    """
    Structured output returned by the Epic Generation Agent.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "epics": [
                    {
                        "epic_id": "EPIC-001",
                        "title": "User Authentication",
                        "features": [
                            "User Login",
                            "Forgot Password",
                            "OTP Verification"
                        ],
                        "one_line_story": "As a customer, I want to securely log in so that I can safely access my account.",
                        "dependencies": [
                            "OTP Service",
                            "SMS Gateway"
                        ],
                        "priority": "Critical"
                    },
                    {
                        "epic_id": "EPIC-002",
                        "title": "Fund Transfer",
                        "features": [
                            "Transfer Money",
                            "Transaction History"
                        ],
                        "one_line_story": "As a customer, I want to transfer money so that I can make secure online payments.",
                        "dependencies": [
                            "Payment Gateway"
                        ],
                        "priority": "High"
                    }
                ]
            }
        }
    )

    epics: list[Epic] = Field(
        default_factory=list,
        description="Generated Agile Epics."
    )
   # ==========================================================
# Epic Generation Agent
# ==========================================================

class EpicGenerationAgent(
    BaseAgent[dict[str, Any] | str, EpicGenerationOutput]
):
    """
    Generate Agile Epics from validated business requirements.

    Input:
        RequirementAnalysisOutput (dict or JSON string)

    Output:
        EpicGenerationOutput
    """

    output_schema = EpicGenerationOutput

    def __init__(
        self,
        prompt_manager: PromptManager | None = None,
        llm_service: LLMService | None = None,
    ) -> None:

        super().__init__("EpicGenerationAgent")

        self.prompt_manager = (
            prompt_manager or PromptManager()
        )
        self.llm_service = (
            llm_service or LLMService(self.prompt_manager)
        )

    async def execute(
        self,
        payload: dict[str, Any] | str,
    ) -> EpicGenerationOutput:
        """
        Execute the Epic Generation Agent.
        """

        return await self._generate_epics(payload)

    async def _generate_epics(
        self,
        requirement_analysis: dict[str, Any] | str,
    ) -> EpicGenerationOutput:

        try:

            serialized_input = self._serialize(
                requirement_analysis
            )

            prompt = (
                self.prompt_manager.get_epic_generation_prompt(
                    serialized_input
                )
            )

            system_prompt = (
                self.prompt_manager
                .get_epic_generation_system_prompt()
            )

            output = await self.llm_service.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                response_schema=self.output_schema,
            )
            return self._normalize_output(output)

        except (
            ValidationError,
            json.JSONDecodeError,
        ) as exc:

            _logger.error(
                "Epic generation response validation failed: %s",
                exc,
                exc_info=True,
            )

            raise EpicGenerationAgentError(
                "Epic generation returned invalid JSON "
                "or schema incompatible output."
            ) from exc

        except LLMServiceError as exc:

            _logger.error(
                "Epic generation LLM call failed: %s",
                exc,
                exc_info=True,
            )

            raise EpicGenerationAgentError(
                "Epic generation failed while invoking the LLM."
            ) from exc

        except Exception as exc:

            _logger.error(
                "Unexpected Epic generation failure: %s",
                exc,
                exc_info=True,
            )

            raise EpicGenerationAgentError(
                "Epic generation failed due to an unexpected backend error."
            ) from exc

    @staticmethod
    def _normalize_output(output: EpicGenerationOutput) -> EpicGenerationOutput:
        """Remove duplicate assignments without changing the response contract."""
        seen_features: set[str] = set()
        for epic in output.epics:
            unique_features: list[str] = []
            for feature in epic.features:
                cleaned = " ".join(feature.split())
                key = cleaned.casefold().rstrip(".")
                if cleaned and key not in seen_features:
                    seen_features.add(key)
                    unique_features.append(cleaned)
            epic.features = unique_features

            unique_dependencies: list[str] = []
            seen_dependencies: set[str] = set()
            for dependency in epic.dependencies:
                cleaned = " ".join(dependency.split())
                key = cleaned.casefold().rstrip(".")
                if cleaned and key not in seen_dependencies:
                    seen_dependencies.add(key)
                    unique_dependencies.append(cleaned)
            epic.dependencies = unique_dependencies

            story = " ".join(epic.one_line_story.split())
            epic.one_line_story = re.split(r"(?<=[.!?])\s+", story, maxsplit=1)[0]

        return output

    @staticmethod
    def _serialize(
        data: dict[str, Any] | BaseModel | str,
    ) -> str:

        if isinstance(data, str):
            return data

        if isinstance(data, BaseModel):
            return json.dumps(
                data.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )

        return json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:

        stripped = text.strip()

        if stripped.startswith("```"):

            first_newline = stripped.find("\n")

            if first_newline != -1:
                stripped = stripped[first_newline + 1:]

            if stripped.endswith("```"):
                stripped = stripped[:-3]

        return stripped.strip()
