"""
Prompt template for chunk context labeling.
"""

from __future__ import annotations


class ContextLabelingPrompt:
    """
    Builds the context labeling prompt for semantic chunks.
    """

    _TEMPLATE = """Assign a concise business context label to each chunk.

Rules:
- Return only valid JSON. Do not include markdown or explanations.
- Label every chunk exactly once using its chunk_id.
- Each context must be 1-3 words.
- Contexts must represent the business domain or feature area.
- Do not classify chunks as Functional Requirements or Non-Functional Requirements.
- Do not extract requirements, write user stories, or analyze acceptance criteria.
- Use labels such as Authentication, User Management, Order Processing, Payment,
  Reporting, Inventory, Notifications, Administration, or another concise
  domain-specific label when those examples do not fit.

Output schema:
{{
  "labels": [
    {{"chunk_id": "string", "context": "string"}}
  ]
}}

Chunks:
{chunks}"""

    @classmethod
    def build(cls, chunks: str) -> str:
        """
        Return the formatted context labeling prompt.
        """

        return cls._TEMPLATE.format(chunks=chunks)
