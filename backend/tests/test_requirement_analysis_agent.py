from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.requirement_analysis_agent import RequirementAnalysisOutput
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
