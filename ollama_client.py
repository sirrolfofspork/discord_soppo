"""
HTTP client for the local Ollama API (chat completion, non-streaming).

Callers pass all settings in; this module does not import application config.

Qwen 3.5 (and similar) may return ``message.thinking`` when reasoning is enabled.
We set ``think: false`` on ``/api/chat`` so the model answers in ``message.content``
for normal chat. Only ``content`` is returned to the bot; ``thinking`` is never sent
to Discord.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Raised when Ollama returns an error or unexpected response."""


async def ollama_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.9,
    top_p: float = 0.9,
    max_tokens: int = 160,
    timeout_seconds: float = 90.0,
) -> str:
    """
    Call Ollama's `/api/chat` endpoint and return the assistant's text.

    Parameters
    ----------
    base_url:
        e.g. http://localhost:11434 (no trailing slash)
    model:
        Must match a name from ``ollama list`` (e.g. ``qwen3.5:4b``).
    messages:
        Chat messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    temperature, top_p, max_tokens:
        Passed to Ollama as ``options`` (``num_predict`` maps from ``max_tokens``).
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": max_tokens,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response else 0
        body = (e.response.text[:500] if e.response is not None else "").strip()
        if status == 404:
            logger.error("Ollama HTTP 404: %s", body or "(empty body)")
            hint = (
                f"Model may be missing. Install with: ollama pull {model} "
                f"(or set OLLAMA_MODEL in .env to a tag from `ollama list`)."
            )
            logger.error("%s", hint)
            raise OllamaError(
                f"Ollama HTTP 404: {body or 'not found'}. {hint}"
            ) from e
        logger.error("Ollama HTTP error: %s %s", status, body)
        raise OllamaError(f"Ollama HTTP {status}: {body}") from e
    except httpx.RequestError as e:
        logger.exception("Ollama request failed: %s", e)
        raise OllamaError(f"Could not reach Ollama at {url}: {e}") from e

    message = data.get("message")
    if not isinstance(message, dict):
        logger.error("Unexpected Ollama response (no message dict). Full payload: %s", data)
        raise OllamaError("Ollama response missing 'message' object")

    raw_content = message.get("content")
    if isinstance(raw_content, str):
        text = raw_content.strip()
        if text:
            return text

    logger.error(
        "Ollama message.content missing, empty, or whitespace-only. Full payload: %s",
        data,
    )
    raise OllamaError("Ollama returned empty content")
