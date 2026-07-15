from __future__ import annotations

import logging
import time
from typing import Optional, Protocol, Tuple

from app.config.settings import settings

logger = logging.getLogger("app.config.model_routing")


class CooldownState:
    """Tracks the circuit-breaker cooldown status of a provider/model pair."""
    def __init__(self) -> None:
        self._cooldowns: dict[tuple[str, str], float] = {}

    def mark_cooldown(self, provider: str, model: str, reset_window_seconds: float) -> None:
        """Mark a provider/model as cooling down until the current time + reset window."""
        expiry = time.time() + reset_window_seconds
        self._cooldowns[(provider, model)] = expiry
        logger.warning(f"Circuit breaker: Marked {provider}/{model} in cooldown for {reset_window_seconds}s.")

    def is_cooling_down(self, provider: str, model: str) -> bool:
        """Check if a provider/model is currently in its cooldown window."""
        expiry = self._cooldowns.get((provider, model), 0.0)
        return time.time() < expiry

    def get_remaining_cooldown(self, provider: str, model: str) -> float:
        """Get the remaining cooldown time in seconds."""
        expiry = self._cooldowns.get((provider, model), 0.0)
        remaining = expiry - time.time()
        return max(0.0, remaining)


# Global singleton for cooldown state
global_cooldown_state = CooldownState()


def resolve_model_chain_for_agent(agent_name: str) -> tuple[tuple[str, str], ...]:
    """
    B4.2: Resolves the ordered fallback chain of (provider, model) for a given agent.
    """
    if agent_name == "segmentation":
        return settings.model_routing.segmentation_chain
    elif agent_name == "epic":
        return settings.model_routing.epic_chain
    elif agent_name == "user_story":
        return settings.model_routing.user_story_chain
    elif agent_name == "validation":
        return settings.model_routing.validation_chain
    else:
        # Default fallback chain if unknown agent
        return (
            ("groq", "llama-3.1-8b-instant"),
            ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        )


def get_available_model(agent_name: str) -> Optional[tuple[str, str]]:
    """
    Gets the first model in the fallback chain that is NOT currently cooling down.
    """
    chain = resolve_model_chain_for_agent(agent_name)
    for provider, model in chain:
        if not global_cooldown_state.is_cooling_down(provider, model):
            return provider, model
    
    # If all are cooling down, we might want to just return the primary and let it fail, 
    # or return None to explicitly fail without calling. Let's return the primary so 
    # transport layer retry wait can kick in if it's the only option.
    logger.error(f"All models in chain for {agent_name} are cooling down. Yielding primary anyway.")
    return chain[0] if chain else None


# ---------------------------------------------------------
# Interface Hook for llm_client.py
# ---------------------------------------------------------

class RateLimitHeaders(Protocol):
    """Protocol representing response headers for rate limits."""
    def get(self, key: str, default: str | None = None) -> str | None: ...


def proactive_throttle_decision(
    provider: str, 
    model: str, 
    headers: RateLimitHeaders, 
    estimated_request_tokens: int
) -> bool:
    """
    Reads live response headers (e.g., x-ratelimit-remaining-tokens) and decides 
    whether the *next* call should be held back.
    
    Returns True if throttle (cooldown) was applied, False otherwise.
    This hook should be called by llm_client.py after every response to update state.
    """
    # Specifically for Groq's token-based limits
    remaining_tokens_str = headers.get("x-ratelimit-remaining-tokens")
    reset_tokens_str = headers.get("x-ratelimit-reset-tokens")
    
    if remaining_tokens_str and reset_tokens_str:
        try:
            remaining_tokens = int(remaining_tokens_str)
            
            # Use 's' at the end to parse as float (Groq sends something like '0.123s')
            reset_str = reset_tokens_str.rstrip('s')
            reset_seconds = float(reset_str)
            
            # If the remaining tokens are dangerously low for the *next* request
            # We proactively trigger a cooldown circuit-breaker
            if remaining_tokens < estimated_request_tokens:
                logger.warning(
                    f"Proactive Throttle: {provider}/{model} only has {remaining_tokens} "
                    f"tokens remaining. Next request est {estimated_request_tokens}. "
                    f"Applying circuit breaker for {reset_seconds}s."
                )
                global_cooldown_state.mark_cooldown(provider, model, reset_seconds)
                return True
                
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse rate limit headers: {e}")
            
    return False

def handle_429_circuit_breaker(provider: str, model: str, retry_after_seconds: float) -> None:
    """
    Hook to be called by llm_client.py when a 429 response is actually received.
    Marks the endpoint as cooling down so subsequent calls route to the fallback chain.
    """
    global_cooldown_state.mark_cooldown(provider, model, retry_after_seconds)
