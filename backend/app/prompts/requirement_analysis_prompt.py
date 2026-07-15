"""
Prompt template for requirement analysis.
"""

from __future__ import annotations


class RequirementAnalysisPrompt:
    """
    Builds the requirement analysis prompt.
    """

    _TEMPLATE = """Analyze only the provided requirement chunks and extract the fields below.

Category rules:
- actors: Real people, personas, teams, roles, or external systems that interact with, operate, administer, build, or receive value from the solution. Do not classify goals, objectives, outcomes, capabilities, activities, conversations, deliverables, or abstract concepts as actors. Examples such as Website Visitors, Enterprise Customers, Sales Team, Marketing Team, CMS Administrators, Developers, and Designers are valid only when supported by the chunks.
- functional_requirements: Every explicit capability, action, page, feature, service, analysis activity, content requirement, or deliverable the project must provide. Check specifically for strategy and messaging, audience definition, competitive analysis, sitemap, content architecture, branding, website pages, AI service offerings, technical features, and deliverables. Preserve document wording where possible. Do not invent missing capabilities.
- non_functional_requirements: Only explicitly stated quality attributes or measurable qualities, including performance, scalability, maintainability, compatibility, responsiveness, SEO readiness, reliability, usability, and security. Do not include business goals, features, deliverables, or general aspirations.
- dependencies: Only explicit implementation prerequisites, integrations, inputs, services, tools, or approvals. Include CMS, analytics, SEO, QA, branding assets, or similar items only when the chunks state or clearly require them as implementation dependencies.
- business_goals: Desired business outcomes, strategic objectives, or value the project is intended to achieve. Keep these separate from functional and non-functional requirements.
- constraints: Only explicit limits or restrictions on timeline, scope, technology, compliance, operation, or delivery. Preserve timeline and scope constraints. Do not infer budget, staffing, resource, or technology limitations.
- edge_cases: Realistic exceptional, boundary, or failure scenarios directly supported by an identified requirement or explicit constraint. Do not create hypothetical scenarios that are not grounded in the chunks.

Perform self-validation within this same response before returning the final JSON:
- Remove duplicate and semantically equivalent entries within every field.
- Ensure complete functional-requirement coverage across all chunks.
- Check that each entry is supported by specific chunk wording.
- Move misclassified entries to the correct field; never repeat an entry across categories.
- Do not hallucinate, broaden, or add unsupported information.
- Preserve original wording and business intent where possible.
- Use an empty list when a category has no supported entries.
- Return only valid JSON matching the schema.
- Do not include the self-validation notes, explanations, markdown, or text outside the JSON.

Output schema:
{{
  "actors": [],
  "functional_requirements": [],
  "non_functional_requirements": [],
  "dependencies": [],
  "business_goals": [],
  "edge_cases": [],
  "constraints": []
}}

Requirement chunks:
{chunks}"""

    @classmethod
    def build(cls, chunks: str) -> str:
        """
        Return the formatted requirement analysis prompt.
        """

        return cls._TEMPLATE.format(chunks=chunks)
