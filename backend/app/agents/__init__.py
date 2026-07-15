from app.agents.exceptions import BackendAgentError, RequirementAnalysisAgentError

__all__ = [
    "BackendAgentError",
    "RequirementAnalysisAgent",
    "RequirementAnalysisAgentError",
]


def __getattr__(name: str):
    if name == "RequirementAnalysisAgent":
        from app.agents.requirement_analysis_agent import RequirementAnalysisAgent

        return RequirementAnalysisAgent
    raise AttributeError(f"module 'app.agents' has no attribute {name!r}")
