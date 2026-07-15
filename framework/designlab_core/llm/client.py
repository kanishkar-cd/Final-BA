"""
designlab_core.llm.client
~~~~~~~~~~~~~~~~~~~~~~~~~~
LLM abstraction layer. All accelerators call generate_response() —
never a provider SDK directly.

This keeps provider details (Anthropic, OpenAI, etc.) completely hidden.
Swapping the underlying model requires zero changes in accelerator code.

Usage:
    from designlab_core.llm.client import generate_response

    result = await generate_response(
        prompt="Generate a user story for login feature",
        model_name="claude-sonnet",   # friendly alias from config.yaml
    )
    print(result.content)
    print(result.model_used)
    print(result.tokens_used)


Status: COMPLETE — provider routing, retry, and timeout logic implemented.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import anthropic
import openai
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from designlab_core.llm.exceptions import (
    LLMProviderError,
    LLMRetryExhausted,
    LLMTimeoutError,
)
from designlab_core.utilities.config import get_config
from designlab_core.utilities.env import get_env
from designlab_core.utilities.logger import get_logger

_logger = get_logger("llm.client")


# ── Return Type ───────────────────────────────────────────────────────────────


@dataclass
class LLMResponse:
    """
    Standardised response returned by generate_response().

    All accelerators work with this object — never with raw provider responses.
    """

    content: str
    """The text content returned by the LLM."""

    model_used: str
    """The actual model ID that handled the request (resolved from alias)."""

    tokens_used: int = 0
    """Total tokens consumed (prompt + completion). 0 if provider doesn't report."""

    metadata: dict = field(default_factory=dict)
    """Any extra provider-specific data worth preserving for debugging."""


# ── Provider Detection ────────────────────────────────────────────────────────


def _detect_provider(model_id: str) -> str:
    """
    Determine the LLM provider from a resolved model ID.

    Supports 'provider/model_id' format from config.yaml.
    
    Args:
        model_id: The resolved model identifier.

    Returns:
        Provider name string (e.g. "anthropic", "openai", "groq", "cerebras").
    """
    if "/" in model_id:
        return model_id.split("/", 1)[0]

    # Backward compatibility for models without a provider prefix
    if model_id.startswith("claude"):
        return "anthropic"
    if model_id.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"

    raise LLMProviderError(
        f"Cannot determine provider for model '{model_id}'. "
        f"Model ID must include a 'provider/' prefix or start with 'claude' or 'gpt-'. "
        f"To fix this, update your config.yaml mapping to use 'provider/model_id'."
    )


# ── Retry Logic ───────────────────────────────────────────────────────────────


def _is_retryable(exc: BaseException) -> bool:
    """
    Determine whether an exception is retryable.

    Retryable (transient):
        - Rate limit errors (429)
        - Server errors (500+)
        - Connection/network errors

    Non-retryable (permanent):
        - Authentication errors (401)
        - Bad request errors (400)
        - Permission errors (403)
        - Not found (404)
    """
    # Anthropic retryable errors
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.InternalServerError):
        return True
    if isinstance(exc, anthropic.APIConnectionError):
        return True

    # OpenAI retryable errors
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.InternalServerError):
        return True
    if isinstance(exc, openai.APIConnectionError):
        return True

    return False


# ── Provider Callers ──────────────────────────────────────────────────────────


async def _call_anthropic(
    prompt: str,
    model_id: str,
    api_key: str,
    system_prompt: str | None,
    max_tokens: int,
) -> LLMResponse:
    """
    Send a request to the Anthropic Messages API.

    Uses anthropic.AsyncAnthropic for non-blocking I/O.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)

    kwargs: dict = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    if system_prompt:
        kwargs["system"] = system_prompt

    _logger.debug(
        f"Calling Anthropic: model={model_id}, "
        f"max_tokens={max_tokens}, prompt_len={len(prompt)}"
    )

    response = await client.messages.create(**kwargs)

    # Extract text content from the response
    content = ""
    # pyrefly: ignore [missing-attribute]
    for block in response.content:
        if block.type == "text":
            content += block.text

    # Calculate total tokens
    tokens_used = 0
    # pyrefly: ignore [missing-attribute]
    if response.usage:
        # pyrefly: ignore [missing-attribute]
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return LLMResponse(
        content=content,
        # pyrefly: ignore [missing-attribute]
        model_used=response.model,
        tokens_used=tokens_used,
        metadata={
            "provider": "anthropic",
            # pyrefly: ignore [missing-attribute]
            "stop_reason": response.stop_reason,
            # pyrefly: ignore [missing-attribute]
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            # pyrefly: ignore [missing-attribute]
            "output_tokens": response.usage.output_tokens if response.usage else 0,
        },
    )


async def _call_openai(
    prompt: str,
    model_id: str,
    api_key: str,
    system_prompt: str | None,
    max_tokens: int,
    base_url: str | None = None,
    provider_name: str = "openai",
) -> LLMResponse:
    """
    Send a request to the OpenAI Chat Completions API.

    Uses openai.AsyncOpenAI for non-blocking I/O.
    """
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    messages: list[dict[str, str]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    _logger.debug(
        f"Calling {provider_name.capitalize()}: model={model_id}, "
        f"max_tokens={max_tokens}, prompt_len={len(prompt)}"
    )

    # pyrefly: ignore [no-matching-overload]
    response = await client.chat.completions.create(
        model=model_id,
        messages=messages,
        max_tokens=max_tokens,
    )

    # Extract content from the first choice
    content = response.choices[0].message.content or ""

    # Calculate total tokens
    tokens_used = 0
    if response.usage:
        tokens_used = response.usage.total_tokens

    return LLMResponse(
        content=content,
        model_used=response.model,
        tokens_used=tokens_used,
        metadata={
            "provider": provider_name,
            "finish_reason": response.choices[0].finish_reason,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": (
                response.usage.completion_tokens if response.usage else 0
            ),
        },
    )


# ── Interface ─────────────────────────────────────────────────────────────────


async def generate_response(
    prompt: str,
    *,
    model_name: str | None = None,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
) -> LLMResponse:
    """
    Send a prompt to an LLM and return a standardised response.

    This is the ONLY function accelerators should call for LLM interaction.

    Args:
        prompt:        The user prompt / instruction to send to the model.
        model_name:    Friendly model alias defined in config.yaml under llm.models.
                       Examples: "claude-sonnet", "claude-haiku", "gpt-4o".
                       Falls back to config.llm.default_model if not recognised.
        system_prompt: Optional system-level instruction prepended to the conversation.
                       Use this to set role/persona context.
        max_tokens:    Maximum tokens to generate in the response.

    Returns:
        LLMResponse with .content, .model_used, .tokens_used, .metadata.

    Raises:
        LLMTimeoutError:  If the request exceeds the configured timeout.
        LLMProviderError: If the provider returns a non-retryable error (e.g. 401, 400).
        LLMRetryExhausted: If all retry attempts are exhausted (e.g. 429, 500).

    Example:
        response = await generate_response(
            prompt="Write a user story for the login screen.",
            model_name="claude-sonnet",
            system_prompt="You are a senior BA. Output valid JSON only.",
        )
        story_json = response.content
    """
    cfg = get_config()
    env = get_env()

    # Step 1: Resolve model alias to full model ID
    # model_name defaults to None since it is now optional in the signature
    model_name = model_name or cfg.llm.default_model
    resolved_model_id = cfg.resolve_model(model_name)
    _logger.info(
        f"Resolved model alias: '{model_name}' → '{resolved_model_id}'"
    )
    
    # Step 1.5: Set defaults from env if not provided
    max_tokens = max_tokens or env.llm_max_tokens

    # Step 2: Detect provider from model ID and extract actual model string
    provider = _detect_provider(resolved_model_id)
    model_id = resolved_model_id.split("/", 1)[1] if "/" in resolved_model_id else resolved_model_id

    # Step 3: Get API key for the provider
    api_key = env.get_llm_key(provider)

    # Step 4: Build the retry-wrapped caller
    max_retries = env.llm_max_retries
    retry_wait = cfg.llm.retry_wait_seconds
    timeout_seconds = env.llm_timeout_seconds

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=retry_wait, min=retry_wait, max=retry_wait * env.llm_retry_max_multiplier),
        reraise=True,
    )
    # pyrefly: ignore [bad-return]
    async def _call_with_retry() -> LLMResponse:
        """Inner function wrapped with tenacity retry logic."""
        if provider == "anthropic":
            return await _call_anthropic(
                prompt=prompt,
                model_id=model_id,
                api_key=api_key,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
            )
        elif provider == "openai":
            return await _call_openai(
                prompt=prompt,
                model_id=model_id,
                api_key=api_key,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
            )
        elif provider == "groq":
            # 1. Fetch fallback chains from the global config object
            groq_chain_cfg = cfg.llm.routing.groq_chain
            cerebras_chain_cfg = cfg.llm.routing.cerebras_chain
            
            # 2. Build the unique sequence
            attempts = [
                ("groq", model_id, "https://api.groq.com/openai/v1")
            ]
            seen_models = {model_id}
            
            for item in groq_chain_cfg:
                m_id = item.split("/", 1)[1] if "/" in item else item
                if m_id not in seen_models:
                    attempts.append(("groq", m_id, "https://api.groq.com/openai/v1"))
                    seen_models.add(m_id)
                    
            for item in cerebras_chain_cfg:
                m_id = item.split("/", 1)[1] if "/" in item else item
                if m_id not in seen_models:
                    attempts.append(("cerebras", m_id, "https://api.cerebras.ai/v1"))
                    seen_models.add(m_id)
            
            # 3. Cache API keys outside the retry loop
            api_keys_cache: dict[str, str | Exception] = {}
            for cur_prov, _, _ in attempts:
                if cur_prov not in api_keys_cache:
                    try:
                        api_keys_cache[cur_prov] = env.get_llm_key(cur_prov)
                    except ValueError as e:
                        api_keys_cache[cur_prov] = e

            # 4. Execute the attempts sequentially with enhanced logging
            total_attempts = len(attempts)
            for i, (cur_prov, cur_model, cur_url) in enumerate(attempts):
                cur_key_or_exc = api_keys_cache[cur_prov]
                if isinstance(cur_key_or_exc, Exception):
                    # Raise the configuration error only if we actually reach this fallback
                    raise cur_key_or_exc
                if not isinstance(cur_key_or_exc, str):
                    raise ValueError(f"Invalid API key type for provider {cur_prov}")
                cur_key: str = cur_key_or_exc
                
                attempt_num = i + 1
                _logger.info(
                    f"Attempt {attempt_num}/{total_attempts} | "
                    f"Provider: {cur_prov.capitalize()} | "
                    f"Model: {cur_model} | Status: Calling"
                )
                
                try:
                    response = await _call_openai(
                        prompt=prompt,
                        model_id=cur_model,
                        api_key=cur_key,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        base_url=cur_url,
                        provider_name=cur_prov,
                    )
                    _logger.info(
                        f"Attempt {attempt_num} succeeded | "
                        f"Provider: {cur_prov.capitalize()} | "
                        f"Model: {cur_model}"
                    )
                    return response
                except Exception as exc:
                    _logger.warning(
                        f"Attempt {attempt_num} failed | "
                        f"Reason: {exc}"
                    )
                    if _is_retryable(exc) and attempt_num < total_attempts:
                        next_prov, next_model, _ = attempts[i+1]
                        _logger.info(
                            f"Retrying Attempt {attempt_num + 1} | "
                            f"Provider: {next_prov.capitalize()} | "
                            f"Model: {next_model}"
                        )
                        continue
                    
                    if attempt_num == total_attempts and _is_retryable(exc):
                        _logger.error(f"All {total_attempts} attempts exhausted. Final failure on {cur_prov.capitalize()} ({cur_model}).")
                    raise
            
            # This should logically never be reached because the list has at least one item
            # But we add it to satisfy the type checker's return path analysis
            raise LLMProviderError("No models were available to attempt.")
        else:
            raise LLMProviderError(f"Unsupported provider: {provider}")

    # Step 5: Execute with timeout
    try:
        _logger.info(
            f"Sending request to {provider}: model={model_id}, "
            f"timeout={timeout_seconds}s, max_retries={max_retries}"
        )

        async with asyncio.timeout(timeout_seconds):
            response = await _call_with_retry()

        _logger.info(
            f"Response received: model={response.model_used}, "
            f"tokens={response.tokens_used}, "
            f"content_len={len(response.content)}"
        )
        return response

    except TimeoutError:
        _logger.error(
            f"Request timed out after {timeout_seconds}s: "
            f"model={model_id}, provider={provider}"
        )
        raise LLMTimeoutError(
            f"LLM request timed out after {timeout_seconds} seconds. "
            f"Model: {model_id}, Provider: {provider}. "
            f"Consider increasing LLM_TIMEOUT_SECONDS in your .env file."
        )

    except (anthropic.AuthenticationError, openai.AuthenticationError) as exc:
        _logger.error(f"Authentication failed for {provider}: {exc}")
        raise LLMProviderError(
            f"Authentication failed for provider '{provider}'. "
            f"Check that {provider.upper()}_API_KEY is valid in your .env file. "
            f"Original error: {exc}"
        ) from exc

    except (anthropic.BadRequestError, openai.BadRequestError) as exc:
        _logger.error(f"Bad request to {provider}: {exc}")
        raise LLMProviderError(
            f"Bad request to provider '{provider}': {exc}. "
            f"Model: {model_id}."
        ) from exc

    except (anthropic.PermissionDeniedError, openai.PermissionDeniedError) as exc:
        _logger.error(f"Permission denied by {provider}: {exc}")
        raise LLMProviderError(
            f"Permission denied by provider '{provider}': {exc}. "
            f"Model: {model_id}."
        ) from exc

    except (anthropic.NotFoundError, openai.NotFoundError) as exc:
        _logger.error(f"Model not found on {provider}: {exc}")
        raise LLMProviderError(
            f"Model '{model_id}' not found on provider '{provider}': {exc}."
        ) from exc

    except Exception as exc:
        # If we get here after retries were exhausted, wrap as LLMRetryExhausted
        if _is_retryable(exc):
            _logger.error(
                f"All {max_retries} retry attempts exhausted for {provider}: {exc}"
            )
            raise LLMRetryExhausted(
                f"All {max_retries} retry attempts exhausted for provider '{provider}'. "
                f"Model: {model_id}. Last error: {exc}"
            ) from exc

        # Unexpected error — wrap as generic provider error
        _logger.error(f"Unexpected error from {provider}: {exc}", exc_info=True)
        raise LLMProviderError(
            f"Unexpected error from provider '{provider}': {exc}. "
            f"Model: {model_id}."
        ) from exc
