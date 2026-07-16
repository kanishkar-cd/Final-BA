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
        score = 100.0
        
        # Acceptance Criteria Completeness
        if not story.acceptance_criteria:
            score -= 30.0
        elif len(story.acceptance_criteria) < 2:
            score -= 10.0
            
        # Presence of business rules
        if not story.business_rules:
            score -= 10.0
            
        # Missing fields / Story structure quality
        if not story.description or len(story.description.strip()) < 10:
            score -= 10.0
        if not story.goal or len(story.goal.strip()) < 5:
            score -= 5.0
        if not story.business_value or len(story.business_value.strip()) < 5:
            score -= 5.0
            
        # Requirement-to-story mapping quality
        if not story.epic_mapping:
            score -= 5.0
        if not story.feature_mapping:
            score -= 5.0
        if not story.requirement_mapping:
            score -= 5.0
            
        # Traceability & Requirement coverage
        if not story.traceability or not story.traceability.feature_refs:
            score -= 15.0
            
        # INVEST compliance
        if story.invest_compliance:
            invest = story.invest_compliance
            invest_flags = [
                invest.independent,
                invest.negotiable,
                invest.valuable,
                invest.estimable,
                invest.small,
                invest.testable,
            ]
            for flag in invest_flags:
                if not flag:
                    score -= 3.0
        else:
            score -= 18.0
            
        # Validation results penalties
        severity_penalty = {
            IssueSeverity.INFO: 2.0,
            IssueSeverity.WARNING: 6.0,
            IssueSeverity.ERROR: 16.0,
            IssueSeverity.CRITICAL: 25.0,
        }
        story_issues = [issue for issue in issues if issue.story_id == story.id]
        score -= sum(severity_penalty[issue.severity] for issue in story_issues)
        
        # Ensure between 0 and 100, then convert to float between 0.0 and 1.0
        final_score = max(0.0, min(100.0, score)) / 100.0
        return round(final_score, 2)

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
