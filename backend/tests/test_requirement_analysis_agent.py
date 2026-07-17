from __future__ import annotations

from pathlib import Path
import asyncio
import sys
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.requirement_analysis_agent import ActorRequirementMapping, RequirementAnalysisOutput
from app.prompts.prompt_manager import PromptManager
from app.prompts.requirement_analysis_prompt import RequirementAnalysisPrompt


def test_requirement_analysis_output_includes_edge_cases_and_constraints() -> None:
    output = RequirementAnalysisOutput.model_validate(
        {
            "actors": ["User"],
            "functional_requirements": ["Users can sign in with OTP."],
            "non_functional_requirements": ["OTP is delivered within 60 seconds."],
            "dependencies": ["OTP Service"],
            "business_goals": ["Secure access"],
            "edge_cases": ["OTP expires before the user completes sign-in."],
            "constraints": ["OTP delivery depends on the configured provider."],
        }
    )

    assert output.edge_cases == ["OTP expires before the user completes sign-in."]
    assert output.constraints == ["OTP delivery depends on the configured provider."]


def test_requirement_analysis_prompt_requests_new_fields_in_json_schema() -> None:
    prompt = RequirementAnalysisPrompt.build("Users can sign in with OTP.")

    assert "- edge_cases:" in prompt
    assert "- constraints:" in prompt
    assert '"edge_cases": []' in prompt
    assert '"constraints": []' in prompt
    assert '"actor_requirement_mappings"' in prompt
    assert "supporting chunk IDs" in prompt
    assert "Return only valid JSON matching the schema." in prompt


def test_prompt_manager_requirement_analysis_system_prompt_mentions_new_fields() -> None:
    system_prompt = PromptManager.get_requirement_analysis_system_prompt()

    assert "edge cases" in system_prompt
    assert "constraints" in system_prompt
    assert "Return only valid JSON with no markdown." in system_prompt


def test_requirement_prompt_enforces_evidence_bound_categories() -> None:
    prompt = RequirementAnalysisPrompt.build("Website visitors browse service pages.")

    assert "Do not classify goals" in prompt
    assert "Every explicit capability" in prompt
    assert "Only explicitly stated quality attributes" in prompt
    assert "Do not infer budget, staffing, resource" in prompt
    assert "directly supported by an identified requirement" in prompt


def test_merge_outputs_deduplicates_case_and_whitespace_variants() -> None:
    from app.agents.requirement_analysis_agent import RequirementAnalysisAgent

    merged = RequirementAnalysisAgent._merge_outputs(
        [
            RequirementAnalysisOutput(actors=["Marketing Team"]),
            RequirementAnalysisOutput(actors=["  marketing   team  "]),
        ]
    )

    assert merged.actors == ["Marketing Team"]


def test_merge_outputs_preserves_distinct_actor_requirement_mappings() -> None:
    from app.agents.requirement_analysis_agent import RequirementAnalysisAgent

    merged = RequirementAnalysisAgent._merge_outputs(
        [
            RequirementAnalysisOutput(
                actor_requirement_mappings=[
                    ActorRequirementMapping(
                        actor="Merchant",
                        requirement="Merchant manages catalog inventory.",
                        chunk_refs=["CHUNK-MERCHANT"],
                    )
                ]
            ),
            RequirementAnalysisOutput(
                actor_requirement_mappings=[
                    ActorRequirementMapping(
                        actor="Buyer",
                        requirement="Buyer searches the product catalog.",
                        chunk_refs=["CHUNK-BUYER"],
                    )
                ]
            ),
        ]
    )

    assert [mapping.actor for mapping in merged.actor_requirement_mappings] == [
        "Merchant",
        "Buyer",
    ]


def test_extracts_all_numbered_use_cases_from_two_persona_sections() -> None:
    from app.agents.requirement_analysis_agent import RequirementAnalysisAgent

    chunks = [
        {
            "chunk_id": "CHUNK-1",
            "content": (
                "Merchant Use Cases 1. Log in 2. View inventory 3. Add New Product "
                "4. Update Inventory 5. View Sales Reports 6. View Order Status 7. "
            ),
        },
        {
            "chunk_id": "CHUNK-2",
            "content": (
                "Message system (merchant end) Buyer Use Cases 1. Log in 2. Homepage "
                "3. Search for Products 4. Add Product to Cart "
                "5. Communicate with merchants / add reviews 6. Checkout and Payment "
                "7. Message system (buyer) System Requirements 1. Authentication"
            ),
        },
    ]
    llm_output = RequirementAnalysisOutput(
        actors=["Merchant", "Buyer"],
        actor_requirement_mappings=[
            ActorRequirementMapping(actor="Merchant", requirement="Log in"),
            ActorRequirementMapping(actor="Buyer", requirement="Log in"),
        ],
    )
    llm_service = AsyncMock()
    llm_service.execute = AsyncMock(return_value=llm_output)

    result = asyncio.run(RequirementAnalysisAgent(llm_service=llm_service).run(chunks))

    expected = {
        "Merchant": [
            "Log in",
            "View inventory",
            "Add New Product",
            "Update Inventory",
            "View Sales Reports",
            "View Order Status",
            "Message system (merchant end)",
        ],
        "Buyer": [
            "Log in",
            "Homepage",
            "Search for Products",
            "Add Product to Cart",
            "Communicate with merchants / add reviews",
            "Checkout and Payment",
            "Message system (buyer)",
        ],
    }
    actual = {
        actor: [
            mapping.requirement
            for mapping in result.actor_requirement_mappings
            if mapping.actor == actor
        ]
        for actor in expected
    }

    assert actual == expected
    assert len(result.actor_requirement_mappings) == 14
    assert all(mapping.chunk_refs for mapping in result.actor_requirement_mappings)
