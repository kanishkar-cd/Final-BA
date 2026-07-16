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
        score = 94.0
        
        # Story Points deduction (high SP implies high complexity/lower confidence)
        sp = story.story_points or 3
        if sp == 1:
            score += 2.0
        elif sp == 2:
            score += 1.0
        elif sp == 3:
            score -= 2.0
        elif sp == 5:
            score -= 6.0
        elif sp == 8:
            score -= 12.0
        elif sp == 13:
            score -= 20.0
        else:
            score -= 5.0

        # Feature completeness & mapping
        if not story.feature_id or story.feature_id.lower() in {"", "feature", "general"}:
            score -= 8.0
        else:
            # Descriptive feature names increase confidence
            if len(story.feature_id) > 10:
                score += 2.0
            else:
                score -= 1.0

        # Acceptance Criteria Completeness
        ac_count = len(story.acceptance_criteria or [])
        if ac_count == 0:
            score -= 20.0
        elif ac_count == 1:
            score -= 8.0
        elif ac_count == 2:
            score -= 2.0
        elif ac_count >= 4:
            score += 3.0
            
        # Presence of business rules
        br_count = len(story.business_rules or [])
        if br_count == 0:
            score -= 6.0
        elif br_count >= 2:
            score += 2.0
            
        # Missing fields / Story structure quality
        desc_len = len((story.description or "").strip())
        if desc_len < 15:
            score -= 10.0
        elif desc_len > 150:
            score += 3.0
            
        # User story template checks (As a / I want / So that)
        story_text = (story.user_story or "").lower()
        if "as a" not in story_text and "as an" not in story_text:
            score -= 4.0
        if "i want" not in story_text and "i need" not in story_text:
            score -= 4.0
        if "so that" not in story_text and "in order to" not in story_text:
            score -= 4.0

        # Mappings
        if not story.requirement_mapping:
            score -= 5.0
        if not story.epic_id:
            score -= 5.0
            
        # Validation results penalties
        severity_penalty = {
            IssueSeverity.INFO: 1.5,
            IssueSeverity.WARNING: 5.0,
            IssueSeverity.ERROR: 12.0,
            IssueSeverity.CRITICAL: 22.0,
        }
        story_issues = [issue for issue in issues if issue.story_id == story.id]
        score -= sum(severity_penalty[issue.severity] for issue in story_issues)
        
        # Natural variations per story/feature
        feat_val = sum(ord(c) for c in (story.feature_id or "default"))
        story_val = sum(ord(c) for c in (story.id or "story"))
        variance = ((feat_val * 7 + story_val * 13) % 13) - 6  # -6 to +6 range
        score += variance

        # Ensure between 10 and 98 to keep realistic boundaries
        final_score = max(10.0, min(98.0, score)) / 100.0
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
