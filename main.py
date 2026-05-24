"""
SOPPO_Python — Discord bot with configurable LLM backend (Ollama or OpenAI).

Run:  python main.py
Requires: Python 3.11+, `.env` with DISCORD_BOT_TOKEN.
If LLM_BACKEND=ollama: Ollama running and OLLAMA_MODEL pulled.
If LLM_BACKEND=openai: OPENAI_API_KEY set.
"""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from bot import run_sync
from config import load_config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    load_dotenv()

    try:
        config = load_config()
    except ValueError as e:
        logging.getLogger(__name__).error("%s", e)
        sys.exit(1)

    run_sync(config)


if __name__ == "__main__":
    main()
