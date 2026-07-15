from __future__ import annotations

import os
import time
import json
import asyncio
import logging
import contextvars
from datetime import datetime, timezone
from typing import Any, TypeVar, Type

from pydantic import BaseModel, ValidationError
import httpx
import openai
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.prompts.prompt_manager import PromptManager
from app.cache.cache_service import CacheService
from app.utils import shutdown

# Logger configurations
logger = logging.getLogger("app.shared.llm_client")
audit_logger = logging.getLogger("app.shared.llm_client.audit")

# Configure a file handler for execution metadata auditing
os.makedirs("logs", exist_ok=True)
audit_handler = logging.FileHandler("logs/ai_execution.log", encoding="utf-8")
audit_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)

# Context variable to hold execution metadata for the current context (e.g. LangGraph workflow node)
ai_execution_metadata: contextvars.ContextVar[list[dict[str, Any]]] = contextvars.ContextVar(
    "ai_execution_metadata", default=[]
)

T = TypeVar("T", bound=BaseModel)


class LLMServiceError(Exception):
    """Base exception for LLMService."""
    pass


class LLMServiceTimeoutError(LLMServiceError):
    """LLM request timed out."""
    pass


class LLMServiceProviderError(LLMServiceError):
    """LLM provider returned an error."""
    pass


class LLMServiceJSONError(LLMServiceError):
    """Failed to parse or validate JSON response."""
    pass


class LLMServiceAuthenticationError(LLMServiceError):
    """LLM API key is invalid or unauthorized (401)."""
    pass


class LLMServiceConfigurationError(LLMServiceError):
    """LLM configuration is invalid or API key is missing."""
    pass


def _is_retryable_exception(exc: Exception) -> bool:
    """Determine if the exception is transient and should be retried."""
    if isinstance(exc, openai.RateLimitError):
        body = getattr(exc, "body", None)
        error_code = body.get("code") if isinstance(body, dict) else None
        message = str(exc).lower()
        # Billing/quota exhaustion is permanent until the account changes;
        # retrying only delays the response and repeats a billable API call.
        return error_code != "insufficient_quota" and "tokens per day" not in message
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, (openai.APIConnectionError, anthropic.APIConnectionError)):
        return True
    if isinstance(exc, (openai.APITimeoutError, anthropic.APITimeoutError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 500, 502, 503, 504):
        return True
    if isinstance(exc, httpx.RequestError):
        return True
    return False


class LLMService:
    """Centralized execution service for AI model integration."""

    def __init__(self, prompt_manager: PromptManager | None = None, cache_service: CacheService | None = None) -> None:
        self.prompt_manager = prompt_manager or PromptManager()
        self.cache = cache_service or CacheService()

    def _get_env_vars(self) -> dict[str, Any]:
        """Dynamically resolve configuration parameters from env variables."""
        return {
            "provider": os.getenv("MODEL_PROVIDER", "openai").lower(),
            "model_name": os.getenv("MODEL_NAME", "gpt-4o"),
            "temperature": float(os.getenv("MODEL_TEMPERATURE", "0.2")),
            "max_tokens": int(os.getenv("MODEL_MAX_TOKENS", "4096")),
            "timeout": float(os.getenv("MODEL_TIMEOUT", "60.0")),
            "top_p": float(os.getenv("MODEL_TOP_P", "1.0")),
        }

    @staticmethod
    def _infer_provider_from_model_name(model_name: str | None) -> str | None:
        """Infer provider from a known model naming pattern."""
        if not model_name:
            return None

        normalized = model_name.strip().lower()
        if not normalized:
            return None

        groq_models = {
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
        }
        if normalized in groq_models:
            return "groq"

        if normalized in {"llama3.1-8b", "gemma2-9b-it", "gpt-oss-120b", "zai-glm-4.7"}:
            return "cerebras"

        if ":free" in normalized or normalized.startswith("openrouter/"):
            return "openrouter"

        if normalized.startswith("gpt-"):
            return "openai"
        if normalized.startswith("claude-"):
            return "anthropic"
        if normalized.startswith("gemini-"):
            return "gemini"

        return None

    async def execute(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_schema: Type[T] | None = None,
        prompt_version: str = "v1",
        **kwargs: Any,
    ) -> T | str:
        """
        Execute an inference request through the centralized execution layer.

        Args:
            prompt: User-level input prompt.
            system_prompt: System-level role / context prompt.
            response_schema: Optional Pydantic model for structured outputs.
            prompt_version: Version tag of the prompt template being used.

        Returns:
            Parsed Pydantic model if response_schema is provided, else raw text string.
        """
        config = self._get_env_vars()
        
        # Override config via kwargs if supplied
        explicit_provider = kwargs.get("provider")
        model_name = kwargs.get("model_name") or config["model_name"]
        inferred_provider = self._infer_provider_from_model_name(model_name)
        provider = explicit_provider or inferred_provider or config["provider"]
        temperature = kwargs.get("temperature") if kwargs.get("temperature") is not None else config["temperature"]
        max_tokens = kwargs.get("max_tokens") if kwargs.get("max_tokens") is not None else config["max_tokens"]
        timeout = kwargs.get("timeout") if kwargs.get("timeout") is not None else config["timeout"]
        top_p = kwargs.get("top_p") if kwargs.get("top_p") is not None else config["top_p"]
        response_format = kwargs.get("response_format")
        reasoning_effort = kwargs.get("reasoning_effort", "low")

        # Cache identity must include generation settings and the structured
        # schema. Otherwise a response truncated at an old token limit is reused
        # after the caller increases max_tokens or changes its output contract.
        schema_name = (
            f"{response_schema.__module__}.{response_schema.__qualname__}"
            if response_schema
            else "text"
        )
        cache_prompt = json.dumps(
            {
                "prompt": prompt,
                "system_prompt": system_prompt or "",
                "prompt_version": prompt_version,
                "schema": schema_name,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "response_format": response_format,
                "reasoning_effort": reasoning_effort,
                "cache_version": 2,
            },
            sort_keys=True,
            default=str,
        )

        start_time = time.perf_counter()
        retry_count = 0
        success = False
        error_msg = None
        raw_response = ""
        tokens_used = 0

        # Check Cache before calling provider
        cached_response = await self.cache.get_ai_response(provider, model_name, temperature, cache_prompt)
        if cached_response:
            logger.info(f"Cache hit for {provider} {model_name}")
            raw_response = cached_response.get("content", "")
            tokens_used = cached_response.get("tokens", 0)
            success = True
            latency = (time.perf_counter() - start_time) * 1000.0
            
            # Log execution metadata (cached)
            metadata = {
                "model_name": model_name,
                "provider": provider,
                "tokens": tokens_used,
                "latency": round(latency, 2),
                "prompt_version": prompt_version,
                "execution_time": datetime.now(timezone.utc).isoformat(),
                "retry_count": 0,
                "success": True,
                "error": None,
                "cached": True,
            }
            audit_logger.info(json.dumps(metadata))
            current_log = ai_execution_metadata.get()
            current_log.append(metadata)
            ai_execution_metadata.set(current_log)
            
            # Parse structured output if schema exists
            if response_schema:
                repaired_json = self._strip_markdown_and_repair_json(raw_response)
                try:
                    parsed_output = response_schema.model_validate_json(repaired_json)
                    return parsed_output
                except (ValidationError, json.JSONDecodeError) as exc:
                    error_msg = f"JSON validation failed on cached response: {exc}. Raw JSON: {repaired_json}"
                    # A malformed cached value must be treated as a cache miss;
                    # the provider can still return a complete replacement.
                    logger.warning("Ignoring invalid structured cache entry: %s", error_msg)
                    cached_response = None
            if cached_response:
                return raw_response

        # Resolve api key based on provider
        api_key = os.getenv(f"{provider.upper()}_API_KEY")
        if not api_key and provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key and provider != "ollama":
            # fallback to framework's env helper if possible
            try:
                # pyrefly: ignore [missing-import]
                from designlab_core.utilities.env import get_env
                api_key = get_env().get_llm_key(provider)
            except Exception:
                pass

        # Validate API key is present before request (except for ollama)
        if not api_key and provider != "ollama":
            error_msg = f"API key is missing for provider '{provider}'. Please configure {provider.upper()}_API_KEY in your environment."
            logger.error(error_msg)
            raise LLMServiceConfigurationError(error_msg)

        @retry(
            retry=retry_if_exception(_is_retryable_exception),
            stop=stop_after_attempt(int(os.getenv("MODEL_MAX_RETRIES", "3"))),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True,
        )
        async def _execute_request() -> tuple[str, int]:
            nonlocal retry_count
            
            # Use tenacity's attempt count if retrying
            try:
                # Count retries
                if retry_count > 0:
                    logger.warning(f"Retrying request to {provider} (attempt {retry_count + 1})")
            except Exception:
                pass

            if provider == "anthropic":
                client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)
                response = await client.messages.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    system=system_prompt or "",
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                content = response.content[0].text
                input_tokens = response.usage.input_tokens if response.usage else 0
                output_tokens = response.usage.output_tokens if response.usage else 0
                return content, (input_tokens + output_tokens)

            elif provider == "openai":
                client = openai.AsyncOpenAI(api_key=api_key, timeout=timeout)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return content, tokens

            elif provider == "gemini":
                # Gemini supports OpenAI-compatible API
                base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return content, tokens

            elif provider == "azure":
                azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
                azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
                client = openai.AsyncAzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=azure_endpoint,
                    api_version=azure_version,
                    timeout=timeout,
                )
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return content, tokens

            elif provider == "ollama":
                ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
                client = openai.AsyncOpenAI(api_key="ollama", base_url=ollama_url, timeout=timeout)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return content, tokens

            elif provider == "groq":
                groq_url = "https://api.groq.com/openai/v1"
                resolved_model = model_name
                if any(x in model_name.lower() for x in ["gpt-", "claude-", "gemini-"]):
                    resolved_model = os.getenv("MODEL_NAME") or "llama-3.3-70b-versatile"
                
                client = openai.AsyncOpenAI(api_key=api_key, base_url=groq_url, timeout=timeout)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                response = await client.chat.completions.create(
                    model=resolved_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                )
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return content, tokens

            elif provider == "cerebras":
                client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://api.cerebras.ai/v1",
                    timeout=timeout,
                    max_retries=0,
                )
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                resolved_response_format = response_format
                if resolved_response_format is None and response_schema is not None:
                    # Pydantic schemas may contain documentation-only keys such
                    # as ``example`` that Cerebras strict schemas reject. JSON
                    # mode guarantees valid JSON; response_schema is still
                    # enforced below with Pydantic model validation.
                    resolved_response_format = {"type": "json_object"}
                cerebras_options: dict[str, Any] = {
                    "reasoning_effort": reasoning_effort,
                }
                if resolved_response_format is not None:
                    cerebras_options["response_format"] = resolved_response_format

                fallback_model = os.getenv("CEREBRAS_FALLBACK_MODEL", "gpt-oss-120b")
                candidate_models = list(dict.fromkeys([model_name, fallback_model]))
                response = None
                for candidate_model in candidate_models:
                    try:
                        response = await client.chat.completions.create(
                            model=candidate_model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            top_p=top_p,
                            extra_body=cerebras_options,
                        )
                        break
                    except openai.NotFoundError:
                        if candidate_model == candidate_models[-1]:
                            raise
                        logger.warning(
                            "Cerebras model '%s' is unavailable; retrying with '%s'.",
                            candidate_model,
                            fallback_model,
                        )
                if response is None:  # pragma: no cover - loop always returns or raises
                    raise LLMServiceProviderError("No Cerebras model was available.")
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return content, tokens

            else:
                # Fallback to designlab_core generate_response
                try:
                    # pyrefly: ignore [missing-import]
                    from designlab_core import generate_response as dl_generate_response
                    res = await dl_generate_response(
                        prompt=prompt,
                        model_name=model_name,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                    )
                    return res.content, res.tokens_used
                except Exception as exc:
                    raise LLMServiceProviderError(f"Unsupported provider {provider} or backend call failed: {exc}")

        try:
            # Wrap execution with asyncio.timeout
            async with asyncio.timeout(timeout):
                raw_response, tokens_used = await _execute_request()
            success = True
            logger.info("LLM request executed successfully. Provider: %s, Model: %s, Latency: %.2fms", provider, model_name, (time.perf_counter() - start_time) * 1000.0)
        except asyncio.TimeoutError as exc:
            error_msg = f"LLM request failed due to timeout: Request timed out after {timeout} seconds. Provider: {provider}, Model: {model_name}"
            logger.error(error_msg)
            raise LLMServiceTimeoutError(error_msg) from exc
        except (openai.AuthenticationError, anthropic.AuthenticationError) as exc:
            error_msg = f"LLM request failed due to invalid API key: Provider returned 401 Unauthorized. Provider: {provider}, Model: {model_name}"
            logger.error(error_msg, exc_info=True)
            raise LLMServiceAuthenticationError(error_msg) from exc
        except (openai.APIConnectionError, anthropic.APIConnectionError) as exc:
            error_msg = f"LLM request failed due to network error: Connection issue with {provider}. Model: {model_name}. Details: {exc}"
            logger.error(error_msg, exc_info=True)
            raise LLMServiceProviderError(error_msg) from exc
        except (openai.OpenAIError, anthropic.APIError) as exc:
            if (
                provider == "groq"
                and isinstance(exc, openai.RateLimitError)
                and os.getenv("CEREBRAS_API_KEY", "").strip()
            ):
                fallback_model = os.getenv("CEREBRAS_FALLBACK_MODEL", "llama3.1-8b").strip()
                logger.warning(
                    "Groq rate limit reached; retrying request with Cerebras model '%s'.",
                    fallback_model,
                )
                fallback_kwargs = dict(kwargs)
                fallback_kwargs.update(
                    {
                        "provider": "cerebras",
                        "model_name": fallback_model,
                        "timeout": timeout,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "top_p": top_p,
                    }
                )
                return await self.execute(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    response_schema=response_schema,
                    prompt_version=prompt_version,
                    **fallback_kwargs,
                )
            error_msg = f"LLM request failed due to OpenAI/Anthropic API error: Provider error: {exc}. Provider: {provider}, Model: {model_name}"
            logger.error(error_msg, exc_info=True)
            raise LLMServiceProviderError(error_msg) from exc
        except asyncio.CancelledError as exc:
            if shutdown.is_shutting_down():
                error_msg = f"LLM request cancelled due to server shutdown. Provider: {provider}, Model: {model_name}"
                logger.info(error_msg)
            else:
                error_msg = f"LLM request cancelled (client disconnected or unexpected task cancellation). Provider: {provider}, Model: {model_name}"
                logger.warning(error_msg)
            success = False
            raise
        except Exception as exc:
            error_msg = f"LLM request failed due to unexpected model execution failure: {exc}. Provider: {provider}, Model: {model_name}"
            logger.error(error_msg, exc_info=True)
            raise LLMServiceError(error_msg) from exc
        finally:
            latency = (time.perf_counter() - start_time) * 1000.0
            
            # Log execution metadata
            metadata = {
                "model_name": model_name,
                "provider": provider,
                "tokens": tokens_used,
                "latency": round(latency, 2),
                "prompt_version": prompt_version,
                "execution_time": datetime.now(timezone.utc).isoformat(),
                "retry_count": retry_count,
                "success": success,
                "error": error_msg,
            }
            audit_logger.info(json.dumps(metadata))
            
            # Save metadata to contextvar
            current_log = ai_execution_metadata.get()
            current_log.append(metadata)
            ai_execution_metadata.set(current_log)

            cacheable = success
            if cacheable and response_schema:
                try:
                    response_schema.model_validate_json(
                        self._strip_markdown_and_repair_json(raw_response)
                    )
                except (ValidationError, json.JSONDecodeError):
                    cacheable = False

            if cacheable:
                # Update Cache
                await self.cache.set_ai_response(
                    provider, 
                    model_name, 
                    temperature, 
                    cache_prompt,
                    {"content": raw_response, "tokens": tokens_used}, 
                    ttl=86400
                )

        # Parse structured output if schema exists
        if response_schema:
            repaired_json = self._strip_markdown_and_repair_json(raw_response)
            try:
                parsed_output = response_schema.model_validate_json(repaired_json)
                return parsed_output
            except (ValidationError, json.JSONDecodeError) as exc:
                error_msg = f"JSON validation failed: {exc}. Raw JSON attempted: {repaired_json}"
                logger.error(error_msg)
                raise LLMServiceJSONError(error_msg) from exc

        return raw_response

    @staticmethod
    def _strip_markdown_and_repair_json(text: str) -> str:
        """Extract and clean raw JSON from LLM output, removing markdown fences or wrappers."""
        text = text.strip()
        
        # Remove standard markdown fences
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
        # Find first '{' or '[' and last '}' or ']'
        first_brace = text.find("{")
        first_bracket = text.find("[")
        
        start_idx = -1
        end_idx = -1
        
        if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
            start_idx = first_brace
            end_idx = text.rfind("}")
        elif first_bracket != -1:
            start_idx = first_bracket
            end_idx = text.rfind("]")
            
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]
            
        return text
