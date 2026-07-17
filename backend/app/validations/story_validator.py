from __future__ import annotations

import re

from app.confidence.confidence_service import ConfidenceService
from app.schemas.user_story import (
    IssueSeverity,
    PipelineStatus,
    RegenerationTarget,
    StoryValidationSummary,
    TraceabilityMatrixRow,
    UserStory,
    ValidateUserStoriesRequest,
    ValidationIssue,
    ValidationResult,
)


class UserStoryValidator:
    def __init__(self, confidence_service: ConfidenceService | None = None) -> None:
        self._confidence_service = confidence_service or ConfidenceService()

    def validate(
        self,
        payload: ValidateUserStoriesRequest,
        validated_by: str = "story-validator",
        extra_issues: list[ValidationIssue] | None = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        if extra_issues:
            issues.extend(extra_issues)
        stories = payload.generated_user_stories
        story_ids = [story.id for story in stories]

        if not stories:
            issues.append(_issue("Completeness", "stories", "At least one user story is required."))

        issues.extend(self._validate_duplicates(story_ids))
        for story in stories:
            issues.extend(self._validate_story(story, set(story_ids), payload, validated_by))
        issues.extend(_validate_repeated_acceptance_templates(stories))

        coverage = {
            "requirements": _covers_required([item.id for item in payload.requirements], _story_requirement_refs(stories)),
            "business_rules": _contains_all_required(payload.business_rules, [rule for story in stories for rule in story.business_rules]),
            "acceptance_criteria": _contains_all_required(
                payload.acceptance_criteria,
                [criterion.description for story in stories for criterion in story.acceptance_criteria],
            ),
            "traceability": all(_has_traceability(story) for story in stories),
            "retrieved_chunks": _covers_required([chunk.id for chunk in payload.retrieved_chunks], _story_chunk_refs(stories)),
        }

        if not coverage["requirements"]:
            issues.append(_issue("Coverage", "requirement_mapping", "Not all requirements are mapped to user stories."))
        if not coverage["business_rules"]:
            issues.append(_issue("Business Rules", "business_rules", "Required business rules are not fully covered."))
        if not coverage["acceptance_criteria"]:
            issues.append(_issue("Acceptance Criteria", "acceptance_criteria", "Required acceptance criteria are not fully covered."))
        if not coverage["traceability"]:
            issues.append(_issue("Traceability", "traceability", "Every story must include complete traceability."))
        if payload.retrieved_chunks and not coverage["retrieved_chunks"]:
            issues.append(_issue("Retrieved Chunk Evidence", "retrieved_chunks", "Not all Agent 1 chunks are linked to generated user stories."))

        story_results = self._build_story_results(
            stories=stories,
            issues=issues,
            threshold=payload.confidence_threshold,
        )
        traceability_matrix = [_traceability_row(story) for story in stories]
        failed_story_ids = [result.story_id for result in story_results if not result.passed]
        upstream_issue_categories = _upstream_issue_categories(issues)
        regeneration_target = _regeneration_target(
            failed_story_ids=failed_story_ids,
            upstream_issue_categories=upstream_issue_categories,
            stories=stories,
        )
        criteria_scores = self._confidence_service.criteria_scores(issues)
        confidence = self._confidence_service.confidence_from_criteria(criteria_scores)
        passed = not issues and confidence >= payload.confidence_threshold
        retry_required = regeneration_target in {
            RegenerationTarget.AGENT_1_REQUIREMENT_ANALYSIS,
            RegenerationTarget.AGENT_2_PLANNING,
            RegenerationTarget.AGENT_3_USER_STORY,
        }
        review_required = regeneration_target == RegenerationTarget.HUMAN_REVIEW
        return ValidationResult(
            validation_status=PipelineStatus.VALIDATION_PASSED if passed else PipelineStatus.VALIDATION_FAILED,
            passed=passed,
            confidence_score=confidence,
            threshold=payload.confidence_threshold,
            issues=issues,
            recommendations=_recommendations_for(issues, retry_required, review_required, regeneration_target),
            retry_required=retry_required,
            review_required=review_required,
            regeneration_target=RegenerationTarget.NONE if passed else regeneration_target,
            failed_story_ids=failed_story_ids,
            upstream_issue_categories=upstream_issue_categories,
            story_results=story_results,
            traceability_matrix=traceability_matrix,
            criteria_scores=criteria_scores,
            coverage=coverage,
        )

    def _build_story_results(
        self,
        *,
        stories: list[UserStory],
        issues: list[ValidationIssue],
        threshold: float,
    ) -> list[StoryValidationSummary]:
        results: list[StoryValidationSummary] = []
        for story in stories:
            story_issues = [issue for issue in issues if issue.story_id == story.id]
            story.confidence_score = self._confidence_service.calculate_story(story, issues)
            passed = not story_issues and story.confidence_score >= threshold
            results.append(
                StoryValidationSummary(
                    story_id=story.id,
                    confidence_score=story.confidence_score,
                    passed=passed,
                    retry_required=not passed and story.retry_attempts < 3,
                    review_required=not passed and story.retry_attempts >= 3,
                    retry_attempts=story.retry_attempts,
                    issues=story_issues,
                    criteria_scores=self._confidence_service.story_criteria_scores(story, issues),
                )
            )
        return results

    def _validate_duplicates(self, story_ids: list[str]) -> list[ValidationIssue]:
        return [
            _issue("Duplicate Stories", "id", f"Duplicate user story ID: {story_id}.", story_id=story_id)
            for story_id in sorted({story_id for story_id in story_ids if story_ids.count(story_id) > 1})
        ]

    def _validate_story(
        self,
        story: UserStory,
        known_story_ids: set[str],
        payload: ValidateUserStoriesRequest,
        validated_by: str,
    ) -> list[ValidationIssue]:
        story.traceability.validated_by = validated_by
        issues: list[ValidationIssue] = []
        if not re.fullmatch(r"US-\d{3}", story.id):
            issues.append(_issue("Formatting", "id", "ID must match US-NNN.", story_id=story.id))
        if not _is_agile_story(story.user_story):
            issues.append(
                _issue(
                    "Formatting",
                    "user_story",
                    "User story must follow 'As a <actor>, I want <goal>, so that <benefit>.'",
                    story_id=story.id,
                )
            )
        expected_actor = _expected_actor_for_story(story, payload)
        if expected_actor and _normalize_text(story.persona) != _normalize_text(expected_actor):
            issues.append(
                _issue(
                    "Persona Correctness",
                    "persona",
                    f"Story persona '{story.persona}' does not match mapped actor '{expected_actor}'.",
                    story_id=story.id,
                )
            )
        if story.persona and not _has_source_actor_evidence(story, payload):
            issues.append(
                _issue(
                    "Persona Correctness",
                    "persona",
                    (
                        f"Story persona '{story.persona}' has no supporting actor-to-requirement "
                        "mapping for this capability. Infrastructure or non-functional work must "
                        "not be assigned to a human persona without source evidence."
                    ),
                    story_id=story.id,
                )
            )
        if not story.acceptance_criteria:
            issues.append(_issue("Acceptance Criteria", "acceptance_criteria", "At least one acceptance criterion is required.", story_id=story.id))
        for criterion in story.acceptance_criteria:
            if not _is_given_when_then(criterion.description):
                issues.append(
                    _issue("Acceptance Criteria", "acceptance_criteria", f"{criterion.id} must use Given/When/Then format.", story_id=story.id)
                )
            elif _is_generic_acceptance_criterion(criterion.description):
                issues.append(
                    _warning(
                        "Acceptance Criteria",
                        "acceptance_criteria",
                        f"{criterion.id} uses a generic template without a concrete observable behavior.",
                        story_id=story.id,
                    )
                )
        for dependency in story.dependencies:
            missing_ids = [dep_id for dep_id in dependency.depends_on if dep_id not in known_story_ids]
            if missing_ids:
                issues.append(
                    _issue(
                        "Relationship Integrity",
                        "dependencies",
                        f"Unknown dependency story IDs: {', '.join(missing_ids)}.",
                        story_id=story.id,
                    )
                )
        if not _has_traceability(story):
            issues.append(_issue("Traceability", "traceability", "Traceability links are incomplete.", story_id=story.id))
        issues.extend(_validate_chunk_evidence(story, payload))
        issues.extend(_validate_agent1_business_rules(story, payload))
        issues.extend(_validate_agent1_dependencies(story, payload))
        if not _has_invest_compliance(story):
            issues.append(_issue("INVEST Compliance", "invest_compliance", "Story does not satisfy all INVEST checks.", story_id=story.id))
        if _has_hallucinated_feature(story, payload):
            issues.append(_issue("Hallucination Detection", "feature_mapping", "Story references a feature not supplied by Agent 2.", story_id=story.id))
        return issues


def _issue(category: str, field: str, message: str, story_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(
        severity=IssueSeverity.ERROR,
        category=category,
        story_id=story_id,
        field=field,
        message=message,
        suggested_action="Retry generation or send to human review.",
    )


def _warning(category: str, field: str, message: str, story_id: str | None = None) -> ValidationIssue:
    issue = _issue(category, field, message, story_id)
    issue.severity = IssueSeverity.WARNING
    return issue


def _is_agile_story(text: str) -> bool:
    lower = text.lower()
    return lower.startswith("as a ") and " i want " in lower and " so that " in lower


def _is_given_when_then(text: str) -> bool:
    lower = text.lower()
    return all(token in lower for token in ["given", "when", "then"])


def _expected_actor_for_story(
    story: UserStory,
    payload: ValidateUserStoriesRequest,
) -> str | None:
    traceability = payload.traceability
    for item in traceability.get("one_line_stories", []):
        if not isinstance(item, dict):
            continue
        if item.get("id") == story.one_line_story_id or item.get("feature_id") == story.feature_id:
            actor = str(item.get("actor") or "").strip()
            if actor:
                return actor
    for item in traceability.get("features", []):
        if not isinstance(item, dict) or item.get("id") != story.feature_id:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        actor = str(metadata.get("actor") or "").strip()
        if actor:
            return actor
    return None


def _has_source_actor_evidence(
    story: UserStory,
    payload: ValidateUserStoriesRequest,
) -> bool:
    mappings = payload.traceability.get("actor_requirement_mappings", [])
    if not isinstance(mappings, list) or not mappings:
        return True
    capability_tokens = _meaningful_words(" ".join(filter(None, [
        story.title,
        story.goal,
        *(mapping.name for mapping in story.feature_mapping),
    ])))
    story_actors = {
        _normalize_text(actor)
        for actor in re.split(r"\s*(?:,|/|\band\b)\s*", story.persona or "")
        if actor.strip()
    }
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        mapped_actor = _normalize_text(str(mapping.get("actor") or ""))
        requirement_tokens = _meaningful_words(str(mapping.get("requirement") or ""))
        if mapped_actor in story_actors and capability_tokens.intersection(requirement_tokens):
            return True
    return False


def _meaningful_words(value: str) -> set[str]:
    stop_words = {
        "a", "an", "and", "for", "of", "the", "to", "with", "system",
        "management", "functionality", "capability",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in stop_words
    }


def _is_generic_acceptance_criterion(text: str) -> bool:
    normalized = _normalize_text(text)
    generic_fragments = (
        "behavior associated with that request",
        "when the capability is used",
        "when the system processes the request",
        "then the resulting state is visible",
        "outcome can be verified from the displayed information",
        "produce the observable outcome stated in the mapped source requirement",
    )
    return any(fragment in normalized for fragment in generic_fragments)


def _validate_repeated_acceptance_templates(stories: list[UserStory]) -> list[ValidationIssue]:
    occurrences: dict[str, list[tuple[UserStory, str]]] = {}
    for story in stories:
        for criterion in story.acceptance_criteria:
            key = _acceptance_template_key(criterion.description, story)
            occurrences.setdefault(key, []).append((story, criterion.id))

    issues: list[ValidationIssue] = []
    for repeated in occurrences.values():
        story_ids = {story.id for story, _ in repeated}
        if len(story_ids) < 2:
            continue
        for story, criterion_id in repeated:
            issues.append(
                _warning(
                    "Acceptance Criteria",
                    "acceptance_criteria",
                    f"{criterion_id} repeats the same normalized AC structure across stories.",
                    story_id=story.id,
                )
            )
    return issues


def _acceptance_template_key(text: str, story: UserStory) -> str:
    normalized = _normalize_text(text)
    variable_values = [
        story.persona,
        story.goal,
        story.title,
        *(mapping.name for mapping in story.feature_mapping),
    ]
    for value in sorted((value for value in variable_values if value), key=len, reverse=True):
        normalized = normalized.replace(_normalize_text(value), "<value>")
    return re.sub(r"\b(us|ac|feat|feature|epic)-?\d+\b", "<id>", normalized)


def _has_traceability(story: UserStory) -> bool:
    trace = story.traceability
    return bool(trace.workflow_id and trace.feature_refs and trace.one_line_story_refs)


def _validate_chunk_evidence(story: UserStory, payload: ValidateUserStoriesRequest) -> list[ValidationIssue]:
    if not payload.retrieved_chunks:
        return []

    issues: list[ValidationIssue] = []
    valid_chunk_ids = {chunk.id for chunk in payload.retrieved_chunks}
    story_chunk_refs = set(story.traceability.chunk_refs)
    chunk_ids_used = set(story.chunk_ids_used)
    source_chunk_refs = {reference.id for reference in story.source_chunk_references}
    all_story_chunk_refs = story_chunk_refs | chunk_ids_used | source_chunk_refs

    if not all_story_chunk_refs:
        issues.append(
            _issue(
                "Retrieved Chunk Evidence",
                "chunk_ids_used",
                "Story must reference at least one Agent 1 chunk.",
                story_id=story.id,
            )
        )
        return issues

    unknown_chunk_ids = sorted(all_story_chunk_refs - valid_chunk_ids)
    if unknown_chunk_ids:
        issues.append(
            _issue(
                "Hallucination Detection",
                "chunk_ids_used",
                f"Story references chunk IDs not supplied by Agent 1: {', '.join(unknown_chunk_ids)}.",
                story_id=story.id,
            )
        )

    if chunk_ids_used and story_chunk_refs and chunk_ids_used != story_chunk_refs:
        issues.append(
            _issue(
                "Traceability",
                "chunk_ids_used",
                "chunk_ids_used must match traceability.chunk_refs.",
                story_id=story.id,
            )
        )

    for criterion in story.acceptance_criteria:
        if not valid_chunk_ids.intersection(set(criterion.source_refs)):
            issues.append(
                _issue(
                    "Retrieved Chunk Evidence",
                    "acceptance_criteria",
                    f"{criterion.id} must reference at least one Agent 1 chunk.",
                    story_id=story.id,
                )
            )

    for dependency in story.dependencies:
        if dependency.source_refs and not valid_chunk_ids.intersection(set(dependency.source_refs)):
            issues.append(
                _issue(
                    "Retrieved Chunk Evidence",
                    "dependencies",
                    f"{dependency.id} must reference Agent 1 chunk evidence.",
                    story_id=story.id,
                )
            )

    return issues


def _has_invest_compliance(story: UserStory) -> bool:
    invest = story.invest_compliance
    return all([invest.independent, invest.negotiable, invest.valuable, invest.estimable, invest.small, invest.testable])


def _has_hallucinated_feature(story: UserStory, payload: ValidateUserStoriesRequest) -> bool:
    supplied_features = {
        str(feature["id"])
        for feature in payload.traceability.get("features", [])
        if isinstance(feature, dict) and "id" in feature
    }
    request_feature_ids = {mapping.id for mapping in story.feature_mapping}
    if not supplied_features:
        return False
    return not request_feature_ids.issubset(supplied_features)


def _validate_agent1_business_rules(story: UserStory, payload: ValidateUserStoriesRequest) -> list[ValidationIssue]:
    if not payload.business_rules:
        return []

    allowed_rules = {_normalize_text(rule) for rule in payload.business_rules}
    issues: list[ValidationIssue] = []
    for rule in story.business_rules:
        if _normalize_text(rule) not in allowed_rules:
            issues.append(
                _issue(
                    "Hallucination Detection",
                    "business_rules",
                    f"Business rule is not present in Agent 1 output: {rule}",
                    story_id=story.id,
                )
            )
    return issues


def _validate_agent1_dependencies(story: UserStory, payload: ValidateUserStoriesRequest) -> list[ValidationIssue]:
    if not payload.dependencies:
        return []

    allowed_dependencies = {_normalize_text(dependency) for dependency in payload.dependencies}
    issues: list[ValidationIssue] = []
    for dependency in story.dependencies:
        if dependency.depends_on:
            continue
        if _normalize_text(dependency.description) not in allowed_dependencies:
            issues.append(
                _issue(
                    "Hallucination Detection",
                    "dependencies",
                    f"Dependency is not present in Agent 1 output: {dependency.description}",
                    story_id=story.id,
                )
            )
    return issues


def _covers_required(required: list[str], actual: list[str]) -> bool:
    return not required or set(required).issubset(set(actual))


def _contains_all_required(required: list[str], actual: list[str]) -> bool:
    if not required:
        return True
    actual_text = " ".join(actual).lower()
    return all(item.lower() in actual_text for item in required)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _story_requirement_refs(stories: list[UserStory]) -> list[str]:
    refs: list[str] = []
    for story in stories:
        refs.extend(story.traceability.requirement_refs)
        refs.extend(mapping.id for mapping in story.requirement_mapping)
    return refs


def _story_chunk_refs(stories: list[UserStory]) -> list[str]:
    refs: list[str] = []
    for story in stories:
        refs.extend(story.traceability.chunk_refs)
    return refs


def _traceability_row(story: UserStory) -> TraceabilityMatrixRow:
    missing_links: list[str] = []
    trace = story.traceability
    if not trace.requirement_refs:
        missing_links.append("requirements")
    if not trace.feature_refs:
        missing_links.append("features")
    if not trace.epic_refs:
        missing_links.append("epics")
    if not trace.one_line_story_refs:
        missing_links.append("one_line_stories")
    if not trace.chunk_refs:
        missing_links.append("retrieved_chunks")
    return TraceabilityMatrixRow(
        story_id=story.id,
        requirement_refs=trace.requirement_refs,
        chunk_refs=trace.chunk_refs,
        epic_refs=trace.epic_refs,
        feature_refs=trace.feature_refs,
        one_line_story_refs=trace.one_line_story_refs,
        dependency_refs=trace.dependency_refs,
        missing_links=missing_links,
    )


def _upstream_issue_categories(issues: list[ValidationIssue]) -> list[str]:
    upstream_categories = {
        "Coverage",
        "Business Rules",
        "Hallucination Detection",
        "Retrieved Chunk Evidence",
        "Traceability",
    }
    return sorted({issue.category for issue in issues if issue.category in upstream_categories})


def _regeneration_target(
    *,
    failed_story_ids: list[str],
    upstream_issue_categories: list[str],
    stories: list[UserStory],
) -> RegenerationTarget:
    if not failed_story_ids and not upstream_issue_categories:
        return RegenerationTarget.NONE
    if any(story.retry_attempts >= 3 for story in stories if story.id in failed_story_ids):
        return RegenerationTarget.HUMAN_REVIEW
    if "Hallucination Detection" in upstream_issue_categories or "Business Rules" in upstream_issue_categories:
        return RegenerationTarget.AGENT_2_PLANNING
    if "Coverage" in upstream_issue_categories or "Traceability" in upstream_issue_categories:
        return RegenerationTarget.AGENT_1_REQUIREMENT_ANALYSIS
    return RegenerationTarget.AGENT_3_USER_STORY


def _recommendations_for(
    issues: list[ValidationIssue],
    retry_required: bool,
    review_required: bool,
    regeneration_target: RegenerationTarget,
) -> list[str]:
    if not issues:
        return ["Stories passed validation and are ready for approval."]
    if review_required:
        return ["Send the workflow to human review with validation issues attached."]
    if retry_required:
        return [f"Retry workflow from {regeneration_target.value} using validation issues and traceability gaps as feedback."]
    return ["Resolve validation issues before final approval."]
