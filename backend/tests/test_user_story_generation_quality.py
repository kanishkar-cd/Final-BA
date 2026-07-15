from app.agents.user_story_agent import (
    _as_given_when_then,
    _dedupe_explicit_rules,
    _supported_business_rules,
)
from app.prompts.user_story_prompt import SYSTEM_PROMPT, USER_PROMPT


def test_story_prompt_requires_single_approved_feature_capability() -> None:
    assert "one primary business capability per story" in SYSTEM_PROMPT
    assert "single assigned Feature as the capability" in USER_PROMPT
    assert "system completes successfully" in USER_PROMPT


def test_business_rules_are_deduplicated_and_evidence_bound() -> None:
    supported = ["Content requires approval", " content  requires approval "]
    assert _dedupe_explicit_rules(supported) == ["Content requires approval"]
    assert _supported_business_rules(
        ["Content requires approval", "Invented administrator rule"],
        supported,
    ) == ["Content requires approval"]


def test_acceptance_criterion_is_testable_and_not_generic() -> None:
    criterion = _as_given_when_then(
        "The services page displays the approved service descriptions",
        "Services Page",
    )

    assert criterion.startswith("Given Services Page is available, When")
    assert "Then the services page displays" in criterion
    assert "completes successfully" not in criterion
