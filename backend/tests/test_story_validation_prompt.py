from app.prompts.prompt_manager import PromptManager
from app.agents.story_validation_agent import _validation_prompt_payload
from app.schemas.user_story import (
    RetrievedChunk,
    TraceabilityLink,
    UserStory,
    ValidateUserStoriesRequest,
)


def test_story_validation_prompt_formats_literal_json() -> None:
    prompt = PromptManager().get_story_validation_prompt(
        workflow_id="WF-TEST",
        generated_user_stories=[],
        requirements=[],
        business_rules=[],
        acceptance_criteria=[],
        dependencies=[],
        traceability={},
        retrieved_chunks=[],
    )

    assert '"validation_status": ""' in prompt.user_prompt
    assert '"retry_required": false' in prompt.user_prompt


def test_validation_payload_keeps_all_stories_but_bounds_evidence_text() -> None:
    stories = [
        UserStory(
            id=f"US-{index:03d}",
            epic_id="EPIC-1",
            feature_id=f"FEATURE-{index:03d}",
            title=f"Story {index}",
            user_story="As a visitor, I want to view a service, so that I can evaluate it.",
            description="D" * 5_000,
            chunk_ids_used=[f"CHUNK-{index:03d}"],
            traceability=TraceabilityLink(
                workflow_id="WF-LARGE",
                chunk_refs=[f"CHUNK-{index:03d}"],
            ),
        )
        for index in range(20)
    ]
    request = ValidateUserStoriesRequest(
        workflow_id="WF-LARGE",
        generated_user_stories=stories,
        retrieved_chunks=[
            RetrievedChunk(id=f"CHUNK-{index:03d}", content="E" * 10_000)
            for index in range(20)
        ],
    )

    compact = _validation_prompt_payload(request)

    assert [story["id"] for story in compact["generated_user_stories"]] == [
        story.id for story in stories
    ]
    assert all(len(story["description"]) <= 600 for story in compact["generated_user_stories"])
    assert sum(len(chunk["content"]) for chunk in compact["retrieved_chunks"]) <= 12_000
