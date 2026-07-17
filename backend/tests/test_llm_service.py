from __future__ import annotations

import json
import pytest
import os
from unittest.mock import AsyncMock, patch
from pydantic import BaseModel

import openai
import anthropic
import httpx

from app.shared.llm_client import (
    LLMService,
    LLMServiceError,
    LLMServiceTimeoutError,
    LLMServiceProviderError,
    LLMServiceJSONError,
    ai_execution_metadata,
)


@pytest.fixture(autouse=True)
def provider_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider calls are mocked, but client construction still requires keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

# Test schema for structured responses
class DummySchema(BaseModel):
    name: str
    items: list[str]


@pytest.mark.asyncio
async def test_llm_service_openai_success() -> None:
    # Clear contextvar
    ai_execution_metadata.set([])

    service = LLMService()
    
    dummy_response = AsyncMock()
    dummy_response.choices = [AsyncMock()]
    dummy_response.choices[0].message.content = '{"name": "test", "items": ["a", "b"]}'
    dummy_response.usage.total_tokens = 42

    with patch("openai.resources.chat.completions.AsyncCompletions.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = dummy_response
        res = await service.execute(
            prompt="hello",
            system_prompt="system context",
            response_schema=DummySchema,
            provider="openai",
            model_name="gpt-4o",
        )
        
        assert isinstance(res, DummySchema)
        assert res.name == "test"
        assert res.items == ["a", "b"]

        metadata = ai_execution_metadata.get()
        assert len(metadata) == 1
        assert metadata[0]["model_name"] == "gpt-4o"
        assert metadata[0]["provider"] == "openai"
        assert metadata[0]["tokens"] == 42
        assert metadata[0]["success"] is True


@pytest.mark.asyncio
async def test_llm_service_anthropic_success() -> None:
    ai_execution_metadata.set([])

    service = LLMService()

    dummy_response = AsyncMock()
    dummy_response.content = [AsyncMock()]
    dummy_response.content[0].text = "Hello from Anthropic!"
    dummy_response.content[0].type = "text"
    dummy_response.usage.input_tokens = 10
    dummy_response.usage.output_tokens = 15

    with patch("anthropic.resources.messages.AsyncMessages.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = dummy_response
        res = await service.execute(
            prompt="hi",
            provider="anthropic",
            model_name="claude-3-5-sonnet",
        )

        assert res == "Hello from Anthropic!"
        
        metadata = ai_execution_metadata.get()
        assert len(metadata) == 1
        assert metadata[0]["model_name"] == "claude-3-5-sonnet"
        assert metadata[0]["provider"] == "anthropic"
        assert metadata[0]["tokens"] == 25
        assert metadata[0]["success"] is True


@pytest.mark.asyncio
async def test_llm_service_json_repair() -> None:
    service = LLMService()

    dummy_response = AsyncMock()
    dummy_response.choices = [AsyncMock()]
    # Return JSON wrapped in conversational text and markdown fences
    dummy_response.choices[0].message.content = "Here is your JSON:\n```json\n{\n  \"name\": \"repaired\",\n  \"items\": [\"x\"]\n}\n```\nHope this helps!"
    dummy_response.usage.total_tokens = 100

    with patch("openai.resources.chat.completions.AsyncCompletions.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = dummy_response
        res = await service.execute(
            prompt="repair me",
            response_schema=DummySchema,
            provider="openai",
        )
        
        assert isinstance(res, DummySchema)
        assert res.name == "repaired"
        assert res.items == ["x"]


@pytest.mark.asyncio
async def test_llm_service_retry_on_rate_limit() -> None:
    ai_execution_metadata.set([])
    service = LLMService()

    # Configure patch to raise RateLimitError first, then succeed
    mock_create = AsyncMock()
    
    # Create fake request and response objects for error instantiation
    # openai.RateLimitError(message, response, body)
    fake_response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    rate_limit_error = openai.RateLimitError("Rate limit hit", response=fake_response, body=None)
    
    success_response = AsyncMock()
    success_response.choices = [AsyncMock()]
    success_response.choices[0].message.content = "success after retry"
    success_response.usage.total_tokens = 12

    mock_create.side_effect = [rate_limit_error, success_response]

    with patch("openai.resources.chat.completions.AsyncCompletions.create", mock_create):
        # Temporarily lower retry backoff for testing speed
        with patch.dict(os.environ, {"MODEL_MAX_RETRIES": "2"}):
            res = await service.execute(
                prompt="retry test",
                provider="openai",
                timeout=5.0,
            )
            assert res == "success after retry"
            assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_user_story_generation_agent_uses_llm_service() -> None:
    from app.agents.user_story_agent import UserStoryGenerationAgent, UserStoriesOutput
    from app.schemas.user_story import GenerateUserStoriesRequest, UserStory, TraceabilityLink, PlanningArtifact, OneLineStoryInput
    from unittest.mock import MagicMock
    
    mock_llm = MagicMock()
    dummy_story = UserStory(
        id="US-001",
        feature_id="FEAT-001",
        title="Mock Title",
        user_story="As a user...",
        description="Mock desc",
        traceability=TraceabilityLink(workflow_id="WF-1")
    )
    mock_llm.execute = AsyncMock(return_value=UserStoriesOutput(user_stories=[dummy_story]))
    
    agent = UserStoryGenerationAgent(llm_service=mock_llm)
    request = GenerateUserStoriesRequest(
        workflow_id="WF-1",
        retrieved_chunks=[],
        one_line_stories=[OneLineStoryInput(id="OLS-1", feature_id="FEAT-1", epic_id="EPIC-1", summary="OLS")],
        epics=[PlanningArtifact(id="EPIC-1", name="Epic 1")],
        features=[PlanningArtifact(id="FEAT-1", name="Feature 1")],
    )
    
    stories = await agent.execute(request)
    assert len(stories) == 1
    assert stories[0].id == "US-001"
    assert mock_llm.execute.call_count == 1


@pytest.mark.asyncio
async def test_user_story_provider_failure_returns_no_fabricated_acceptance_criteria() -> None:
    from app.agents.user_story_agent import UserStoryGenerationAgent
    from app.schemas.user_story import GenerateUserStoriesRequest, PlanningArtifact, OneLineStoryInput, RetrievedChunk
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.execute = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    agent = UserStoryGenerationAgent(llm_service=mock_llm)
    request = GenerateUserStoriesRequest(
        workflow_id="WF-PROVIDER-FAILURE",
        retrieved_chunks=[RetrievedChunk(
            id="CHUNK-1",
            content="Unrelated executive-summary text must never become acceptance criteria.",
        )],
        one_line_stories=[OneLineStoryInput(
            id="OLS-1",
            feature_id="FEAT-1",
            epic_id="EPIC-1",
            summary="Search products",
            chunk_refs=["CHUNK-1"],
        )],
        epics=[PlanningArtifact(id="EPIC-1", name="Shopping")],
        features=[PlanningArtifact(id="FEAT-1", name="Product Search")],
    )

    stories = await agent.execute(request)

    assert len(stories) == 1
    assert stories[0].acceptance_criteria == []
    assert stories[0].definition_of_done == []
    assert stories[0].user_story == ""
    assert stories[0].description == ""
    assert stories[0].confidence_score == 0.0
    assert stories[0].metadata["generation_status"] == "FAILED"
    assert stories[0].metadata["fallback_content_generated"] is False

    from app.schemas.user_story import ValidateUserStoriesRequest
    from app.validations.story_validator import UserStoryValidator

    validation = UserStoryValidator().validate(ValidateUserStoriesRequest(
        workflow_id=request.workflow_id,
        generated_user_stories=stories,
        retrieved_chunks=request.retrieved_chunks,
    ))
    assert validation.passed is False
    assert validation.retry_required is True
    assert any(
        issue.field == "acceptance_criteria"
        and "At least one acceptance criterion is required" in issue.message
        for issue in validation.issues
    )


@pytest.mark.asyncio
async def test_empty_provider_output_is_marked_generation_failed() -> None:
    from app.agents.user_story_agent import UserStoriesOutput, UserStoryGenerationAgent
    from app.schemas.user_story import GenerateUserStoriesRequest, PlanningArtifact, OneLineStoryInput
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    mock_llm.execute = AsyncMock(return_value=UserStoriesOutput(user_stories=[]))
    agent = UserStoryGenerationAgent(llm_service=mock_llm)
    request = GenerateUserStoriesRequest(
        workflow_id="WF-EMPTY-PROVIDER-OUTPUT",
        one_line_stories=[OneLineStoryInput(
            id="OLS-1",
            feature_id="FEAT-1",
            epic_id="EPIC-1",
            summary="Search products",
        )],
        epics=[PlanningArtifact(id="EPIC-1", name="Shopping")],
        features=[PlanningArtifact(id="FEAT-1", name="Product Search")],
    )

    stories = await agent.execute(request)

    assert len(stories) == 1
    assert stories[0].acceptance_criteria == []
    assert stories[0].metadata["generation_status"] == "FAILED"
    assert stories[0].metadata["generation_failure_type"] == "empty_provider_output"


@pytest.mark.asyncio
async def test_story_validation_agent_uses_llm_service() -> None:
    from app.agents.story_validation_agent import StoryValidationAgent, AIValidationOutput
    from app.schemas.user_story import ValidateUserStoriesRequest, ValidationIssue, PipelineStatus, UserStory, TraceabilityLink
    from unittest.mock import MagicMock
    
    mock_llm = MagicMock()
    dummy_issue = ValidationIssue(
        category="Semantic",
        field="user_story",
        message="AI found a semantic issue."
    )
    mock_llm.execute = AsyncMock(
        return_value=AIValidationOutput(
            validation_status=PipelineStatus.VALIDATION_FAILED,
            confidence_score=0.5,
            issues=[dummy_issue]
        )
    )
    
    agent = StoryValidationAgent(llm_service=mock_llm)
    dummy_story = UserStory(
        id="US-001",
        feature_id="FEAT-001",
        title="Mock Title",
        user_story="As a user...",
        description="Mock desc",
        traceability=TraceabilityLink(workflow_id="WF-1")
    )
    request = ValidateUserStoriesRequest(
        workflow_id="WF-1",
        generated_user_stories=[dummy_story],
        requirements=[],
        business_rules=[],
        acceptance_criteria=[],
        dependencies=[],
        retrieved_chunks=[],
    )
    
    result = await agent.execute(request)
    assert result.passed is False
    assert any(issue.category == "Semantic" for issue in result.issues)
    assert mock_llm.execute.call_count == 1
