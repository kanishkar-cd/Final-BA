from app.agents.user_story_agent import (
    _as_given_when_then,
    _dedupe_explicit_rules,
    _supported_business_rules,
)
from app.prompts.user_story_prompt import SYSTEM_PROMPT, USER_PROMPT


def test_story_prompt_requires_single_approved_feature_capability() -> None:
    assert "one primary business capability per story" in SYSTEM_PROMPT
    assert "single assigned Feature as the capability" in USER_PROMPT
    assert "capability is used" in USER_PROMPT


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
        actor="Visitor",
        goal="review service descriptions",
    )

    assert criterion.startswith("Given the documented prerequisites for review service descriptions")
    assert "When the Visitor attempts to review service descriptions" in criterion
    assert "Then the services page displays" in criterion
    assert "completes successfully" not in criterion


def test_story_prompt_forbids_feature_substitution_acceptance_templates() -> None:
    assert "PRESERVE PERSONA SCOPE" in SYSTEM_PROMPT
    assert "WRITE CONCRETE ACCEPTANCE CRITERIA" in SYSTEM_PROMPT
    assert "Do not use the Feature name itself" in USER_PROMPT
    assert "happy path plus validation/error and edge/boundary cases" in USER_PROMPT
