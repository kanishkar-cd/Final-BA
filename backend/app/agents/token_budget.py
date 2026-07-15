from __future__ import annotations

import logging
from typing import Any
import tiktoken

from app.config.settings import settings

logger = logging.getLogger("app.agents.token_budget")


def count_tokens(text: str, model_name: str = "cl100k_base") -> int:
    """
    Counts the number of tokens in a text string.
    Falls back to character-based approximation if tiktoken fails.
    """
    try:
        encoding = tiktoken.get_encoding(model_name)
        return len(encoding.encode(text, disallowed_special=()))
    except Exception as e:
        logger.warning(f"tiktoken encoding failed: {e}. Falling back to char count approx.")
        return len(text) // 4


class TokenBudgetManager:
    """
    B4.4: Enforces token budgets and triggers map-reduce splitting when context exceeds the active ceiling.
    """
    
    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self.ceiling = self._resolve_ceiling(provider, model)

    def _resolve_ceiling(self, provider: str, model: str) -> int:
        """
        Dynamically resolves the safe_call_ceiling based on provider and model limits.
        Falls back to a conservative default if not explicitly configured.
        """
        # In a real app, we'd lookup `ProviderModelLimits` from DB or settings.
        # Since it's dynamic, we might have a registry. For now, we simulate the lookup logic.
        
        # Example hardcoded lookups based on the strategy doc if they aren't directly in settings:
        lookup_map = {
            ("groq", "llama-3.1-8b-instant"): 4800,  # 6000 TPM minus 20%
            ("groq", "llama-3.3-70b-versatile"): 9600, # 12000 TPM minus 20%
            ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"): 24000, # 30000 TPM minus 20%
            ("groq", "qwen/qwen3-32b"): 4800, # 6000 TPM minus 20%
        }
        
        # OpenRouter/Cerebras or unknown models fallback
        return lookup_map.get((provider.lower(), model.lower()), 8000)

    def is_within_budget(self, text: str) -> bool:
        """Checks if the text fits within the safe call ceiling."""
        return count_tokens(text) <= self.ceiling

    def ensure_within_budget(self, text: str, split_strategy: str = "map-reduce") -> list[str]:
        """
        If text exceeds ceiling, splits it into multiple safe sub-chunks for map-reduce.
        Returns a list of text chunks. If within budget, returns a single-item list.
        """
        tokens = count_tokens(text)
        if tokens <= self.ceiling:
            return [text]
            
        logger.info(f"Context size ({tokens} tokens) exceeds safe ceiling ({self.ceiling}). Applying {split_strategy}.")
        
        # Simple token-based splitting for map-reduce (splitting by newlines first to preserve some structure)
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for p in paragraphs:
            p_tokens = count_tokens(p)
            if current_tokens + p_tokens > self.ceiling and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [p]
                current_tokens = p_tokens
            else:
                current_chunk.append(p)
                current_tokens += p_tokens
                
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
        # In case a single paragraph is still too big, force split by characters
        final_chunks = []
        for c in chunks:
            if count_tokens(c) > self.ceiling:
                # Roughly split by char approximation
                approx_chars = self.ceiling * 4
                for i in range(0, len(c), approx_chars):
                    final_chunks.append(c[i:i+approx_chars])
            else:
                final_chunks.append(c)
                
        return final_chunks
