"""
Custom exceptions raised by backend agents.
"""

from __future__ import annotations


class BackendAgentError(Exception):
    """
    Base exception for all backend agent failures.
    """


class RequirementAnalysisAgentError(BackendAgentError):
    """
    Raised when requirement analysis fails.
    """


class EpicGenerationAgentError(BackendAgentError):
    """
    Raised when epic generation fails.
    """


class FeatureGenerationAgentError(BackendAgentError):
    """
    Raised when feature generation fails.
    """


class UserStoryGenerationAgentError(BackendAgentError):
    """
    Raised when user story generation fails.
    """


class AcceptanceCriteriaGenerationAgentError(BackendAgentError):
    """
    Raised when acceptance criteria generation fails.
    """


class ValidationAgentError(BackendAgentError):
    """
    Raised when validation of generated artifacts fails.
    """


class TraceabilityAgentError(BackendAgentError):
    """
    Raised when traceability mapping generation fails.
    """