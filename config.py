"""
Load and validate settings from environment variables.

Tune behavior here or in `.env` — variable names match `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Application configuration (immutable after load)."""

    discord_bot_token: str
    llm_backend: str  # "ollama" | "openai" | "lmstudio"
    ollama_model: str
    ollama_url: str
    openai_api_key: str
    openai_model: str
    lmstudio_base_url: str
    lmstudio_api_key: str
    lmstudio_model: str
    discord_allowed_channel_ids: tuple[int, ...]
    discord_channel_name: str
    spontaneous_reply_chance: float
    reply_cooldown_seconds: float
    max_context_messages: int
    max_prompt_chars: int
    # Generation (passed through to llm_client by bot.py)
    temperature: float
    top_p: float
    max_tokens: int
    # Direct-address: natural-language names (comma-separated in .env)
    bot_name_aliases: tuple[str, ...]
    # Discord reply shaping (after model output)
    discord_reply_soft_limit: int
    discord_reply_hard_limit: int
    # Rare "returning user" hint in LLM prompt (wall clock for absence; see bot.py)
    returning_user_threshold_seconds: float
    user_greeting_cooldown_seconds: float
    channel_greeting_cooldown_seconds: float
    returning_user_greeting_chance: float
    # Sliding window: after addressing SOPPO, same user can keep replying without re-mentioning
    inferred_followup_window_seconds: float


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        raise ValueError(
            f"Missing or empty environment variable: {name}. "
            f"Copy .env.example to .env and set it."
        )
    return str(value).strip()


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return float(str(raw).strip())


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(str(raw).strip())


def _parse_bot_name_aliases(raw: str | None) -> tuple[str, ...]:
    """Comma-separated non-empty strings, order preserved (longest-match handled in bot)."""
    if raw is None or not str(raw).strip():
        return ()
    out: list[str] = []
    for part in str(raw).split(","):
        s = part.strip()
        if s:
            out.append(s)
    return tuple(out)


def _parse_channel_ids(raw: str | None) -> tuple[int, ...]:
    """Comma-separated Discord channel IDs. Empty/unset means use name fallback."""
    if raw is None or not str(raw).strip():
        return ()

    out: list[int] = []
    for part in str(raw).split(","):
        s = part.strip()
        if not s:
            continue
        if not s.isdecimal():
            raise ValueError(
                "DISCORD_ALLOWED_CHANNEL_IDS must be a comma-separated list of numeric "
                f"Discord channel IDs (got {s!r})."
            )
        out.append(int(s))
    return tuple(out)


def load_config() -> Config:
    """
    Read configuration from the environment.

    Call after `load_dotenv()` so `.env` values are visible to `os.getenv`.
    """
    token = _require("DISCORD_BOT_TOKEN")

    raw_backend = os.getenv("LLM_BACKEND", "ollama").strip().lower()
    if raw_backend not in ("ollama", "openai", "lmstudio"):
        raise ValueError(
            'LLM_BACKEND must be "ollama", "openai", or "lmstudio" '
            f"(got {raw_backend!r}). See .env.example."
        )
    llm_backend = raw_backend

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:4b").strip()

    openai_model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip()
    openai_key_raw = os.getenv("OPENAI_API_KEY")
    openai_api_key = str(openai_key_raw).strip() if openai_key_raw else ""

    lmstudio_base_url = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1").strip().rstrip("/")
    lmstudio_model = os.getenv("LMSTUDIO_MODEL", "local-model").strip()
    lmstudio_key_raw = os.getenv("LMSTUDIO_API_KEY", "not-needed")
    lmstudio_api_key = str(lmstudio_key_raw).strip() or "not-needed"

    if llm_backend == "openai":
        if not openai_api_key:
            raise ValueError(
                'OPENAI_API_KEY is required when LLM_BACKEND=openai. '
                "Set it in .env (see .env.example)."
            )
    if llm_backend == "lmstudio":
        if not lmstudio_base_url:
            raise ValueError(
                'LMSTUDIO_BASE_URL is required when LLM_BACKEND=lmstudio. '
                "Set it in .env (see .env.example)."
            )
        if not lmstudio_model:
            raise ValueError(
                'LMSTUDIO_MODEL is required when LLM_BACKEND=lmstudio. '
                "Set it in .env (see .env.example)."
            )

    allowed_channel_ids = _parse_channel_ids(os.getenv("DISCORD_ALLOWED_CHANNEL_IDS"))
    channel_name = os.getenv("DISCORD_CHANNEL_NAME", "general").strip()

    chance = _float_env("SPONTANEOUS_REPLY_CHANCE", 0.10)
    chance = max(0.0, min(1.0, chance))

    cooldown = _float_env("REPLY_COOLDOWN_SECONDS", 30.0)
    if cooldown < 0:
        cooldown = 0.0

    max_ctx = _int_env("MAX_CONTEXT_MESSAGES", 20)
    max_ctx = max(2, min(100, max_ctx))

    max_chars = _int_env("MAX_PROMPT_CHARS", 8000)
    max_chars = max(500, min(100_000, max_chars))

    temperature = _float_env("OLLAMA_TEMPERATURE", 0.9)
    temperature = max(0.0, min(2.0, temperature))

    top_p = _float_env("OLLAMA_TOP_P", 0.9)
    top_p = max(0.0, min(1.0, top_p))

    max_tokens = _int_env("OLLAMA_MAX_TOKENS", 160)
    max_tokens = max(16, min(32_768, max_tokens))

    bot_name_aliases = _parse_bot_name_aliases(os.getenv("BOT_NAME_ALIASES"))

    soft_limit = _int_env("DISCORD_REPLY_SOFT_LIMIT", 500)
    hard_limit = _int_env("DISCORD_REPLY_HARD_LIMIT", 1800)
    soft_limit = max(80, min(1900, soft_limit))
    hard_limit = max(soft_limit + 50, min(1999, hard_limit))

    returning_threshold = _float_env("RETURNING_USER_THRESHOLD_SECONDS", 43200.0)
    returning_threshold = max(60.0, returning_threshold)

    user_greet_cd = _float_env("USER_GREETING_COOLDOWN_SECONDS", 86400.0)
    user_greet_cd = max(0.0, user_greet_cd)

    channel_greet_cd = _float_env("CHANNEL_GREETING_COOLDOWN_SECONDS", 14400.0)
    channel_greet_cd = max(0.0, channel_greet_cd)

    greet_chance = _float_env("RETURNING_USER_GREETING_CHANCE", 0.20)
    greet_chance = max(0.0, min(1.0, greet_chance))

    followup_window = _float_env("INFERRED_FOLLOWUP_WINDOW_SECONDS", 180.0)
    followup_window = max(15.0, min(86_400.0, followup_window))

    return Config(
        discord_bot_token=token,
        llm_backend=llm_backend,
        ollama_model=ollama_model,
        ollama_url=ollama_url,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        lmstudio_base_url=lmstudio_base_url,
        lmstudio_api_key=lmstudio_api_key,
        lmstudio_model=lmstudio_model,
        discord_allowed_channel_ids=allowed_channel_ids,
        discord_channel_name=channel_name,
        spontaneous_reply_chance=chance,
        reply_cooldown_seconds=cooldown,
        max_context_messages=max_ctx,
        max_prompt_chars=max_chars,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        bot_name_aliases=bot_name_aliases,
        discord_reply_soft_limit=soft_limit,
        discord_reply_hard_limit=hard_limit,
        returning_user_threshold_seconds=returning_threshold,
        user_greeting_cooldown_seconds=user_greet_cd,
        channel_greeting_cooldown_seconds=channel_greet_cd,
        returning_user_greeting_chance=greet_chance,
        inferred_followup_window_seconds=followup_window,
    )


# --- Tunables (documented defaults; real values come from env in load_config) ---
# LLM_BACKEND                — ollama | openai | lmstudio
# OPENAI_API_KEY             — required if LLM_BACKEND=openai
# OPENAI_MODEL               — e.g. gpt-5.4-mini
# LMSTUDIO_BASE_URL          — e.g. http://localhost:1234/v1
# LMSTUDIO_MODEL             — model name loaded in LM Studio
# LMSTUDIO_API_KEY           — placeholder key for local OpenAI-compatible API (default not-needed)
# DISCORD_ALLOWED_CHANNEL_IDS — comma-separated channel IDs; when set, takes priority over name
# DISCORD_CHANNEL_NAME       — fallback: only this channel name (case-insensitive) is monitored
# SPONTANEOUS_REPLY_CHANCE   — 0.0–1.0, default 0.10
# REPLY_COOLDOWN_SECONDS     — seconds between spontaneous replies after any reply
# MAX_CONTEXT_MESSAGES       — rolling deque size per channel
# MAX_PROMPT_CHARS           — trim older context to stay under this size
# OLLAMA_MODEL               — must match `ollama list` (e.g. qwen3.5:4b)
# OLLAMA_URL                 — e.g. http://localhost:11434
# OLLAMA_TEMPERATURE         — sampling temperature (default 0.9)
# OLLAMA_TOP_P               — nucleus sampling (default 0.9)
# OLLAMA_MAX_TOKENS          — max tokens to generate (num_predict / API max_tokens, default 160)
# BOT_NAME_ALIASES           — comma-separated names that count as addressing the bot
# DISCORD_REPLY_SOFT_LIMIT   — target max length before chunking (default 500)
# DISCORD_REPLY_HARD_LIMIT   — max chars per Discord message chunk (default 1800)
# RETURNING_USER_THRESHOLD_SECONDS    — min wall-clock gap since user's last post (default 12h)
# USER_GREETING_COOLDOWN_SECONDS      — monotonic cooldown before same user gets hint again (24h)
# CHANNEL_GREETING_COOLDOWN_SECONDS   — monotonic cooldown before any hint in channel (4h)
# RETURNING_USER_GREETING_CHANCE      — probability when other checks pass (default 0.20)
# INFERRED_FOLLOWUP_WINDOW_SECONDS    — wall-clock seconds to keep “same user” convo alive (default 180)
# Character prompt           — edit prompts.build_system_prompt() in prompts.py
