from __future__ import annotations

from app.schemas.user_story import ConfidenceCriterionScore, IssueSeverity, UserStory, ValidationIssue


CRITERION_MAX_SCORES = {
    "Completeness": 10.0,
    "Consistency": 10.0,
    "Coverage": 10.0,
    "Business Rules": 10.0,
    "Acceptance Criteria": 10.0,
    "Duplicate Stories": 10.0,
    "Missing Stories": 10.0,
    "Traceability": 10.0,
    "INVEST Compliance": 10.0,
    "Relationship Integrity": 10.0,
    "Formatting": 10.0,
    "Hallucination Detection": 10.0,
    "Retrieved Chunk Evidence": 10.0,
}


class ConfidenceService:
    def calculate(self, stories: list[UserStory], issues: list[ValidationIssue]) -> float:
        if not stories:
            return 0.0

        severity_penalty = {
            IssueSeverity.INFO: 0.02,
            IssueSeverity.WARNING: 0.06,
            IssueSeverity.ERROR: 0.12,
            IssueSeverity.CRITICAL: 0.2,
        }
        penalty = sum(severity_penalty[issue.severity] for issue in issues)
        traceability_bonus = 0.05 if all(story.traceability for story in stories) else 0.0
        invest_bonus = 0.05 if all(_is_invest_compliant(story) for story in stories) else 0.0
        score = 1.0 - min(0.95, penalty) + traceability_bonus + invest_bonus
        return round(max(0.0, min(1.0, score)), 2)

    def calculate_story(self, story: UserStory, issues: list[ValidationIssue]) -> float:
        severity_penalty = {
            IssueSeverity.INFO: 0.02,
            IssueSeverity.WARNING: 0.06,
            IssueSeverity.ERROR: 0.16,
            IssueSeverity.CRITICAL: 0.25,
        }
        story_issues = [issue for issue in issues if issue.story_id == story.id]
        penalty = sum(severity_penalty[issue.severity] for issue in story_issues)
        if not story.traceability or not story.traceability.feature_refs:
            penalty += 0.12
        if not _is_invest_compliant(story):
            penalty += 0.1
        return round(max(0.0, min(1.0, 1.0 - penalty)), 2)

    def criteria_scores(self, issues: list[ValidationIssue]) -> list[ConfidenceCriterionScore]:
        return [
            self._score_category(category, issues)
            for category in CRITERION_MAX_SCORES
        ]

    def story_criteria_scores(
        self,
        story: UserStory,
        issues: list[ValidationIssue],
    ) -> list[ConfidenceCriterionScore]:
        story_issues = [issue for issue in issues if issue.story_id == story.id]
        return self.criteria_scores(story_issues)

    def confidence_from_criteria(self, criteria_scores: list[ConfidenceCriterionScore]) -> float:
        total_score = sum(item.score for item in criteria_scores)
        max_score = sum(item.max_score for item in criteria_scores)
        if max_score == 0:
            return 0.0
        return round(total_score / max_score, 2)

    def _score_category(
        self,
        category: str,
        issues: list[ValidationIssue],
    ) -> ConfidenceCriterionScore:
        category_issues = [issue for issue in issues if issue.category == category]
        max_score = CRITERION_MAX_SCORES[category]
        penalty = sum(_issue_mark_penalty(issue.severity) for issue in category_issues)
        score = round(max(0.0, max_score - penalty), 2)
        return ConfidenceCriterionScore(
            category=category,
            score=score,
            max_score=max_score,
            passed=score == max_score,
            issue_count=len(category_issues),
            details=[issue.message for issue in category_issues],
        )


def _is_invest_compliant(story: UserStory) -> bool:
    invest = story.invest_compliance
    return all(
        [
            invest.independent,
            invest.negotiable,
            invest.valuable,
            invest.estimable,
            invest.small,
            invest.testable,
        ]
    )


def _issue_mark_penalty(severity: IssueSeverity) -> float:
    return {
        IssueSeverity.INFO: 1.0,
        IssueSeverity.WARNING: 2.0,
        IssueSeverity.ERROR: 4.0,
        IssueSeverity.CRITICAL: 7.0,
    }[severity]
