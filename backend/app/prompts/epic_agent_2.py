"""
Prompt template for Epic Generation.
"""

from __future__ import annotations


class EpicGenerationPrompt:
    """
    Builds the Epic Generation prompt.
    """

    _TEMPLATE = """Analyze the provided validated requirement analysis and generate Agile Epics.

Generate a reasonable number of high-level business Epics by grouping related functional requirements into cohesive business capabilities, not technical implementation tasks.

Extract:
- epic_id
- title
- features
- one_line_story
- priority
- dependencies

Perform self-validation within this same response before returning the final JSON:

- Form each Epic around a meaningful business objective; avoid one Epic per requirement or other overly granular groupings.
- Group related functional requirements under the same Epic and keep unrelated business and technical capabilities separate.
- Represent these capability areas whenever supported: Strategy & Foundation, Branding & UI, Website Pages, AI Services, Technical Platform, and SEO. Do not create an area when no extracted functional requirement supports it.
- Every functional requirement must belong to exactly one Epic.
- Do not duplicate requirements across multiple Epics.
- Ensure complete coverage of all functional requirements.
- Treat extracted functional requirements as the only source for features. Ignore business goals during feature assignment unless they explicitly describe implementation work.
- Generate concise and business-oriented Epic titles.
- Generate feature names that preserve the source requirement intent and belong only under that Epic; do not invent or duplicate features.
- Preserve actor_requirement_mappings: populate feature_actors with one entry for every feature, using the actor explicitly associated with that source requirement/use case. Do not use one default actor for all features when multiple actors are supplied.
- Generate exactly one concise, business-oriented sentence in one_line_story for each Epic, derived only from that Epic and its features.
- Assign an appropriate priority (Critical, High, Medium, or Low).
- Include only dependencies explicitly extracted from the requirements.
- Do not hallucinate or add unsupported information.
- Preserve the original business intent.
- Do not generate Acceptance Criteria.
- Return only valid JSON matching the schema.
- Do not include self-validation notes, explanations, markdown, or any text outside the JSON.

Output schema:
{{
  "epics": [
    {{
      "epic_id": "",
      "title": "",
      "features": [],
      "feature_actors": {{}},
      "one_line_story": "",
      "dependencies": [],
      "priority": ""
    }}
  ]
}}

Validated Requirement Analysis:
{requirement_analysis}"""

    @classmethod
    def build(cls, requirement_analysis: str) -> str:
        """
        Return the formatted Epic Generation prompt.
        """

        return cls._TEMPLATE.format(
            requirement_analysis=requirement_analysis
        )
