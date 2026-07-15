from app.agents.epic_agent_2 import Epic, EpicGenerationAgent, EpicGenerationOutput
from app.prompts.epic_agent_2 import EpicGenerationPrompt


def test_epic_prompt_groups_supported_business_capabilities() -> None:
    prompt = EpicGenerationPrompt.build('{"functional_requirements": []}')

    assert "Strategy & Foundation" in prompt
    assert "Technical Platform" in prompt
    assert "Every functional requirement must belong to exactly one Epic" in prompt
    assert "Ignore business goals during feature assignment" in prompt
    assert "one concise, business-oriented sentence" in prompt


def test_epic_output_removes_duplicate_feature_assignments() -> None:
    output = EpicGenerationOutput(
        epics=[
            Epic(
                epic_id="EPIC-001",
                title="Website Experience",
                features=["Service Pages", "Service Pages"],
                one_line_story="Visitors can discover services. This sentence is extra.",
                dependencies=["Brand assets", " brand assets "],
                priority="High",
            ),
            Epic(
                epic_id="EPIC-002",
                title="Technical Platform",
                features=["service pages", "CMS Integration"],
                one_line_story="Administrators can manage website content.",
                dependencies=[],
                priority="Medium",
            ),
        ]
    )

    normalized = EpicGenerationAgent._normalize_output(output)

    assert normalized.epics[0].features == ["Service Pages"]
    assert normalized.epics[1].features == ["CMS Integration"]
    assert normalized.epics[0].dependencies == ["Brand assets"]
    assert normalized.epics[0].one_line_story == "Visitors can discover services."
    assert [epic.epic_id for epic in normalized.epics] == ["EPIC-001", "EPIC-002"]
