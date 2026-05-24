"""
Minimal async client for OpenAI Chat Completions (text only, no tools).

Callers pass the API key and model; this module does not import application config.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import APIError, APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

logger = logging.getLogger(__name__)


class OpenAIClientError(Exception):
    """Raised when the OpenAI API returns an error or empty assistant text."""


def _api_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only role/content keys OpenAI expects."""
    out: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role not in ("system", "user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        out.append({"role": str(role), "content": content})
    return out


async def openai_chat(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.9,
    top_p: float = 0.9,
    max_tokens: int = 160,
    timeout_seconds: float = 90.0,
) -> str:
    """
    Call OpenAI chat completions and return the assistant message text only.

    messages use the same shape as Ollama: role + content strings.
    """
    client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
    api_msgs = _api_messages(messages)
    if not api_msgs:
        raise OpenAIClientError("No valid messages to send to OpenAI")

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=api_msgs,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
    except RateLimitError as e:
        logger.error("OpenAI rate limit: %s", e)
        raise OpenAIClientError(f"OpenAI rate limited: {e}") from e
    except (APIConnectionError, APITimeoutError) as e:
        logger.exception("OpenAI connection failed: %s", e)
        raise OpenAIClientError(f"Could not reach OpenAI API: {e}") from e
    except APIError as e:
        logger.error("OpenAI API error: %s", e)
        raise OpenAIClientError(f"OpenAI API error: {e}") from e

    choice = response.choices[0] if response.choices else None
    if choice is None or choice.message is None:
        logger.error("OpenAI response missing choices: %s", response)
        raise OpenAIClientError("OpenAI returned no choices")

    raw = choice.message.content
    if isinstance(raw, str):
        text = raw.strip()
        if text:
            return text

    logger.error("OpenAI assistant content empty or missing. Response: %s", response)
    raise OpenAIClientError("OpenAI returned empty content")
