from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.shared_intelligence import (
    EvidenceSourceBuilder,
    QualityGates,
    SharedValidators,
)
from app.prompts.prompt_manager import PromptManager
from app.schemas.user_story import (
    PipelineStatus,
    ValidateUserStoriesRequest,
    ValidationIssue,
    ValidationResult,
)
from app.shared.llm_client import LLMService
from app.validations.story_validator import UserStoryValidator

logger = logging.getLogger("agents.story_validation")


class AIValidationOutput(BaseModel):
    """Structured response schema returned by AI semantic validation."""

    validation_status: PipelineStatus
    confidence_score: float
    issues: list[ValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    retry_required: bool = False
    review_required: bool = False


class StoryValidationAgent(BaseAgent[ValidateUserStoriesRequest, ValidationResult]):
    """Agent 4: independent evidence validator for generated user stories."""

    def __init__(
        self,
        validator: UserStoryValidator | None = None,
        prompt_manager: PromptManager | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        super().__init__("agent-4-story-validator")
        self._validator = validator or UserStoryValidator()
        self._prompt_manager = prompt_manager or PromptManager()
        self.llm_service = llm_service or LLMService(self._prompt_manager)

    async def execute(self, payload: ValidateUserStoriesRequest) -> ValidationResult:
        prompt = self._prompt_manager.get_story_validation_prompt(
            **_validation_prompt_payload(payload)
        )

        ai_issues = await self._run_ai_validation(prompt.user_prompt, prompt.system_prompt)
        evidence = EvidenceSourceBuilder.build(payload)
        independent_issues, report = SharedValidators.independent_validate(payload, evidence)
        result = self._validator.validate(
            payload,
            validated_by=self.name,
            extra_issues=[*ai_issues, *independent_issues],
        )
        QualityGates.apply_validation_report(result, report)
        return result

    async def _run_ai_validation(
        self,
        user_prompt: str,
        system_prompt: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        try:
            ai_output = await self.llm_service.execute(
                prompt=user_prompt,
                system_prompt=system_prompt,
                response_schema=AIValidationOutput,
                prompt_version="v1",
            )
            if isinstance(ai_output, AIValidationOutput):
                issues = ai_output.issues
                for issue in issues:
                    issue.source_reference = issue.source_reference or "AI Semantic Analysis"
                    issue.suggested_action = (
                        issue.suggested_action or "Review story content or retry generation."
                    )
        except Exception as exc:
            logger.warning(
                "AI semantic validation failed or timed out: %s. Continuing with independent evidence validation.",
                exc,
                exc_info=True,
            )
        return issues


def _validation_prompt_payload(payload: ValidateUserStoriesRequest) -> dict:
    """Build a bounded semantic-validation view without changing validation data."""
    stories = []
    referenced_chunks: set[str] = set()
    story_description_limit = max(
        120,
        min(600, 12_000 // max(1, len(payload.generated_user_stories))),
    )
    for story in payload.generated_user_stories:
        chunk_refs = list(dict.fromkeys([
            *story.chunk_ids_used,
            *story.traceability.chunk_refs,
        ]))
        referenced_chunks.update(chunk_refs)
        stories.append({
            "id": story.id,
            "epic_id": story.epic_id,
            "feature_id": story.feature_id,
            "title": story.title[:200],
            "user_story": story.user_story[:500],
            "description": story.description[:story_description_limit],
            "acceptance_criteria": [
                {"id": criterion.id, "description": criterion.description[:400]}
                for criterion in story.acceptance_criteria[:5]
            ],
            "business_rules": [rule[:300] for rule in story.business_rules[:10]],
            "dependencies": [
                {
                    "id": dependency.id,
                    "description": dependency.description[:300],
                    "depends_on": dependency.depends_on,
                }
                for dependency in story.dependencies[:10]
            ],
            "requirement_refs": story.traceability.requirement_refs,
            "chunk_refs": chunk_refs,
        })

    requirement_limit = max(100, min(500, 6_000 // max(1, len(payload.requirements))))
    requirements = [
        {
            "id": requirement.id,
            "name": requirement.name,
            "description": (requirement.description or "")[:requirement_limit],
        }
        for requirement in payload.requirements
    ]
    selected_chunks = [
        chunk
        for chunk in payload.retrieved_chunks
        if not referenced_chunks or chunk.id in referenced_chunks
    ]
    chunk_limit = max(120, min(800, 12_000 // max(1, len(selected_chunks))))
    chunks = [
        {
            "id": chunk.id,
            "content": chunk.content[:chunk_limit],
            "source": chunk.source,
        }
        for chunk in selected_chunks
    ]

    return {
        "workflow_id": payload.workflow_id,
        "generated_user_stories": stories,
        "requirements": requirements,
        "business_rules": [rule[:300] for rule in payload.business_rules[:50]],
        "acceptance_criteria": [],
        "dependencies": [dependency[:300] for dependency in payload.dependencies[:50]],
        "traceability": [
            {
                "story_id": story["id"],
                "epic_id": story["epic_id"],
                "feature_id": story["feature_id"],
                "requirement_refs": story["requirement_refs"],
                "chunk_refs": story["chunk_refs"],
            }
            for story in stories
        ],
        "retrieved_chunks": chunks,
    }


__all__ = ["AIValidationOutput", "StoryValidationAgent"]
