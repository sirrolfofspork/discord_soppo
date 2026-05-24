"""
LLM routing: trim context, then call Ollama or OpenAI based on backend.

Main bot code should use ``generate_reply`` and ``trim_messages_to_max_chars`` only.
"""

from __future__ import annotations

from typing import Any, Literal

from ollama_client import OllamaError, ollama_chat
from openai_client import OpenAIClientError, openai_chat

LLMBackend = Literal["ollama", "openai"]

# Re-export for callers that handle errors by backend
__all__ = [
    "LLMBackend",
    "OllamaError",
    "OpenAIClientError",
    "generate_reply",
    "trim_messages_to_max_chars",
]


async def generate_reply(
    *,
    backend: LLMBackend,
    messages: list[dict[str, Any]],
    temperature: float,
    top_p: float,
    max_tokens: int,
    ollama_url: str,
    ollama_model: str,
    openai_api_key: str,
    openai_model: str,
    timeout_seconds: float = 90.0,
) -> str:
    """
    Single entry point for chat completion: Ollama or OpenAI.

    Pass all URL/model/key fields; unused fields for the active backend are ignored.
    """
    if backend == "ollama":
        return await ollama_chat(
            base_url=ollama_url,
            model=ollama_model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
    if backend == "openai":
        return await openai_chat(
            api_key=openai_api_key,
            model=openai_model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unknown LLM backend: {backend!r}")


def trim_messages_to_max_chars(
    messages: list[dict[str, Any]],
    max_chars: int,
) -> list[dict[str, Any]]:
    """
    Keep the system message(s) (if present) plus as many recent non-system messages
    as fit under `max_chars` (counting JSON-ish length of content strings).
    """
    if not messages:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    def msg_len(m: dict[str, Any]) -> int:
        c = m.get("content", "")
        return len(c) if isinstance(c, str) else 0

    system_total = sum(msg_len(m) for m in system_msgs)
    budget = max_chars - system_total
    if budget < 500:
        budget = max(500, max_chars // 2)

    kept: list[dict[str, Any]] = []
    total = 0
    for m in reversed(rest):
        L = msg_len(m)
        if kept and total + L > budget:
            break
        kept.append(m)
        total += L

    kept.reverse()
    return system_msgs + kept
