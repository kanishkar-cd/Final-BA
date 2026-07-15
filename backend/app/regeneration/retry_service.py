from __future__ import annotations

from app.schemas.user_story import PipelineStatus, ValidationResult


class RetryService:
    def should_retry(self, validation: ValidationResult, retry_attempt: int, max_attempts: int) -> bool:
        return validation.retry_required and retry_attempt < max_attempts

    def status_after_validation(
        self,
        validation: ValidationResult,
        retry_attempt: int,
        max_attempts: int,
    ) -> PipelineStatus:
        if validation.passed:
            return PipelineStatus.VALIDATION_PASSED
        if self.should_retry(validation, retry_attempt, max_attempts):
            return PipelineStatus.RETRY_REQUIRED
        return PipelineStatus.REVIEW_REQUIRED
