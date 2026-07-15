from __future__ import annotations

import pytest
import time
from unittest.mock import Mock

from app.agents.token_budget import TokenBudgetManager
from app.config.model_routing import (
    resolve_model_chain_for_agent,
    get_available_model,
    global_cooldown_state,
    proactive_throttle_decision,
    handle_429_circuit_breaker
)
from app.schemas.user_story import UserStory, PlanningArtifact


def test_token_budget_manager_ceiling_resolution():
    """Test that safe call ceiling resolves dynamically based on provider and model."""
    groq_llama3 = TokenBudgetManager("groq", "llama-3.1-8b-instant")
    assert groq_llama3.ceiling == 4800  # Based on lookup map
    
    groq_llama4 = TokenBudgetManager("groq", "meta-llama/llama-4-scout-17b-16e-instruct")
    assert groq_llama4.ceiling == 24000
    
    unknown = TokenBudgetManager("unknown_provider", "unknown_model")
    assert unknown.ceiling == 8000  # Default


def test_token_budget_manager_map_reduce_split():
    """Test map-reduce splitting when context exceeds the active safe ceiling."""
    manager = TokenBudgetManager("groq", "llama-3.1-8b-instant")
    # Force a low ceiling for testing
    manager.ceiling = 100
    
    # Generate text with ~150 tokens (using character approx ~600 chars)
    # 3 paragraphs, ~50 tokens each
    para1 = "a " * 50
    para2 = "b " * 50
    para3 = "c " * 50
    text = f"{para1}\n\n{para2}\n\n{para3}"
    
    chunks = manager.ensure_within_budget(text)
    
    # Should split into at least 2 chunks
    assert len(chunks) > 1
    for chunk in chunks:
        assert manager.is_within_budget(chunk)


def test_model_routing_fallback_chain():
    """Test fallback chain resolution."""
    epic_chain = resolve_model_chain_for_agent("epic")
    assert len(epic_chain) == 3
    assert epic_chain[0] == ("groq", "meta-llama/llama-4-scout-17b-16e-instruct")
    assert epic_chain[1] == ("groq", "llama-3.3-70b-versatile")
    assert epic_chain[2] == ("openrouter", "meta-llama/llama-3.3-70b-instruct:free")


def test_circuit_breaker_and_available_model():
    """Test circuit breaker cooldown logic and its effect on get_available_model."""
    # Reset state
    global_cooldown_state._cooldowns.clear()
    
    # Initially, primary should be available
    provider, model = get_available_model("epic")
    assert provider == "groq"
    assert model == "meta-llama/llama-4-scout-17b-16e-instruct"
    
    # Simulate a 429 on the primary model
    handle_429_circuit_breaker(provider, model, retry_after_seconds=5.0)
    
    assert global_cooldown_state.is_cooling_down(provider, model)
    
    # Now, next available should be the fallback
    provider2, model2 = get_available_model("epic")
    assert provider2 == "groq"
    assert model2 == "llama-3.3-70b-versatile"
    
    # Reset
    global_cooldown_state._cooldowns.clear()


def test_proactive_throttle_decision():
    """Test proactive throttle based on remaining tokens."""
    global_cooldown_state._cooldowns.clear()
    
    # Mock headers for Groq
    mock_headers = Mock()
    mock_headers.get.side_effect = lambda k, default=None: {
        "x-ratelimit-remaining-tokens": "2000",
        "x-ratelimit-reset-tokens": "4.5s"
    }.get(k, default)
    
    # Estimated request is 3000, but only 2000 remaining -> should throttle
    throttled = proactive_throttle_decision(
        provider="groq", 
        model="llama-3.1-8b-instant", 
        headers=mock_headers, 
        estimated_request_tokens=3000
    )
    
    assert throttled is True
    assert global_cooldown_state.is_cooling_down("groq", "llama-3.1-8b-instant")
    
    # Cooldown duration should be roughly 4.5
    remaining = global_cooldown_state.get_remaining_cooldown("groq", "llama-3.1-8b-instant")
    assert 4.0 < remaining <= 4.5
    
    # Reset
    global_cooldown_state._cooldowns.clear()
