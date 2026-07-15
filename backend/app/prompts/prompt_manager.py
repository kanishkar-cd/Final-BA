from __future__ import annotations

import os
from dataclasses import dataclass

from app.prompts.context_labeling_prompt import ContextLabelingPrompt
from app.prompts.epic_agent_2 import EpicGenerationPrompt
from app.prompts.requirement_analysis_prompt import RequirementAnalysisPrompt
from app.prompts.story_validation_prompt import (
    SYSTEM_PROMPT as STORY_VALIDATION_SYSTEM_PROMPT,
    USER_PROMPT as STORY_VALIDATION_USER_PROMPT,
)
from app.prompts.user_story_prompt import (
    SYSTEM_PROMPT as USER_STORY_SYSTEM_PROMPT,
    USER_PROMPT as USER_STORY_USER_PROMPT,
)


@dataclass(frozen=True)
class PromptTemplate:
    system_prompt: str
    user_prompt: str


class PromptManager:
    """Centralized Prompt Manager for all AI agents."""

    USER_STORY = "user_story"
    STORY_VALIDATION = "story_validation"

    def __init__(self) -> None:
        self._prompts = {
            self.USER_STORY: PromptTemplate(
                USER_STORY_SYSTEM_PROMPT,
                USER_STORY_USER_PROMPT,
            ),
            self.STORY_VALIDATION: PromptTemplate(
                STORY_VALIDATION_SYSTEM_PROMPT,
                STORY_VALIDATION_USER_PROMPT,
            ),
        }

    @staticmethod
    def get_requirement_analysis_prompt(chunks: str) -> str:
        return RequirementAnalysisPrompt.build(chunks)

    @staticmethod
    def get_requirement_analysis_system_prompt() -> str:
        return (
            "You are an evidence-bound Business Analyst extracting requirements "
            "from supplied document chunks. Classify real actors, exhaustive explicit "
            "functional requirements, explicit quality attributes, business goals, "
            "constraints, implementation dependencies, and grounded edge cases into "
            "their separate schema fields. Never infer unsupported content. "
            "Return only valid JSON with no markdown."
        )

    @staticmethod
    def get_context_labeling_prompt(chunks: str) -> str:
        return ContextLabelingPrompt.build(chunks)

    @staticmethod
    def get_context_labeling_system_prompt() -> str:
        return (
            "You are an expert Business Analyst labeling semantic document "
            "chunks by business domain. Return only valid JSON with no markdown."
        )

    @staticmethod
    def get_epic_generation_prompt(requirement_analysis: str) -> str:
        return EpicGenerationPrompt.build(requirement_analysis)

    @staticmethod
    def get_epic_generation_system_prompt() -> str:
        return (
            "You are an Enterprise Business Analyst and Agile Product Owner. "
            "Generate high-quality Agile Epics from validated requirements. "
            "Group related functional requirements into meaningful business "
            "capabilities. Return only valid JSON matching the provided schema. "
            "Do not include markdown or explanations."
        )

    @staticmethod
    def get_default_model() -> str:
        # Keep model selection aligned with LLMService. The shared framework's
        # default is a Claude model, which is invalid when the backend provider
        # defaults to OpenAI.
        return os.getenv("MODEL_NAME", "gpt-4o")

    def get_prompt(self, prompt_name: str, **kwargs) -> PromptTemplate:
        if prompt_name not in self._prompts:
            raise ValueError(f"Unknown prompt: {prompt_name}")

        prompt = self._prompts[prompt_name]
        return PromptTemplate(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt.format(**kwargs),
        )

    def get_user_story_prompt(self, **kwargs) -> PromptTemplate:
        return self.get_prompt(self.USER_STORY, **kwargs)

    def get_story_validation_prompt(self, **kwargs) -> PromptTemplate:
        return self.get_prompt(self.STORY_VALIDATION, **kwargs)
