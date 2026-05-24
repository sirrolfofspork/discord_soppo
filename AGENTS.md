# AGENTS.md — SOPPO Discord Bot

## Project Purpose

This project implements **SOPPO**, a Discord chatbot roleplaying as **M4 SOPMOD II** from Girls’ Frontline.

SOPPO should:
- Talk naturally in Discord channels.
- Stay in character.
- Use local or hosted LLM backends.
- Support user profiles, lore injection, and lightweight memory.
- Avoid spammy or intrusive behavior.
- Be easy to run on the Linux Hermes machine.

Project path:

```text
/home/erik-desimone/AI/agents/soppo_discord
```
Agent Operating Rules

Before making changes:

Inspect the current project structure.
Read relevant files before editing.
Do not assume Cursor-era code is current.
Preserve working behavior unless explicitly changing it.
Prefer small, testable edits.
Explain what changed after each task.

Do not rewrite the whole project unless explicitly asked.

Current Concept

The bot listens on Discord and replies as SOPPO.

Desired backend options:

Local LLM backend
Ollama
LM Studio OpenAI-compatible server
llama.cpp server if added later
Hosted LLM backend
OpenAI API
Other API-compatible models if added later

The bot should support switching backends by configuration, not by rewriting bot logic.

## Expected Architecture

Prefer this separation:
bot.py               Discord event handling and response decision logic
config.py            Environment/config loading
prompts.py           SOPPO persona and prompt formatting
llm_client.py         Backend router
ollama_client.py      Ollama backend
lmstudio_client.py    LM Studio/OpenAI-compatible local backend
openai_client.py      OpenAI API backend
lore.py              Lore matching and lore context generation
lore_store.json       Curated GFL lore entries
user_profiles.py      User profile loading
user_profiles.json    Per-user background/profile data
memory.py             Optional channel summaries / memory helpers

If files do not yet exist, create them incrementally.

Backend Rules
Local Backends

Local backends are preferred for cheap, always-on Discord use.

Supported local targets should include:

Ollama /api/chat
LM Studio OpenAI-compatible API endpoint

LM Studio support should be implemented as an OpenAI-compatible local endpoint when possible.

Config should allow something like:
LLM_BACKEND=ollama
# or
LLM_BACKEND=lmstudio
# or
LLM_BACKEND=openai

Hosted Backend

OpenAI API should be treated as a proper paid API backend.

Use environment variables:

OPENAI_API_KEY=
OPENAI_MODEL=

## Discord Behavior Rules

SOPPO should:

Ignore itself.
Respond only in configured channels.
Respond to direct triggers, mentions, aliases, and reply chains.
Support inferred follow-up conversation when a user keeps talking to SOPPO or Sash.
Use cooldowns for spontaneous replies.
Avoid spam.
Avoid @everyone and @here.

Do not make SOPPO greet everyone who comes online. Discord presence behavior is noisy and should not be used unless explicitly requested.

## Prompt and Character Rules

prompts.py owns prompt wording.

Do not scatter personality text through bot.py.

SOPPO should:

Be energetic, mischievous, chaotic, and loyal.
Sound like M4 SOPMOD II, not a generic assistant.
Use short Discord-friendly replies by default.
Avoid long rants unless asked.
Use current-speaker context when available.
Not confuse users with SOPPO herself.

The assistant role is SOPPO. Do not prefix assistant history with [SOPPO]: if structured chat roles are already being used.

## User Profiles

Use Discord user IDs as stable keys.

Display names are for readability only.

Preferred structure:
{
  "717449407573786655": {
    "preferred_name": "SKK",
    "relationship": "Commander / bot creator",
    "notes": [
      "Familiar user",
      "Comfortable with playful teasing"
    ]
  }
}

Inject only the current speaker’s profile into the prompt.

Do not dump all profiles into every prompt.

## Lore Injection

Use curated lore rather than relying on raw model memory.

Lore entries should be short and targeted.

Preferred structure:
{
  "g11": {
    "aliases": ["g11", "g 11"],
    "summary": "Short factual lore summary.",
    "soppo_take": "Short in-character relationship or opinion."
  }
}

Rules:

Match lore by aliases in the current message and possibly recent context.
Inject only relevant lore.
Do not dump the entire lore store.
Do not let automated tools invent large amounts of GFL canon without review.

Cursor/Hermes may build the lore plumbing, but Leva/SKK should author or review actual lore content.

## Memory Rules

Memory layers should be separated:

Stable persona prompt
Current speaker profile
Relevant lore context
Channel summary
Recent chat history
Current message

Do not rely on the LLM to permanently remember facts.

For local models, memory must be app-managed through summaries, profiles, and retrieval.

## Safety and Privacy

Never commit:

Discord bot tokens
OpenAI API keys
OAuth tokens
.env
private logs

.gitignore must include:
.env
*.log
__pycache__/
.venv/
If logs contain private Discord content, treat them as sensitive.

## Development Workflow

Before editing:

git status

If the working tree is dirty, explain what is dirty before making changes.

After editing:

python -m compileall .

If tests exist:

pytest

For dependency changes, update:

requirements.txt
README setup instructions if applicable

## Stop Conditions

Stop and ask before:

deleting existing working bot logic
changing Discord token/auth handling
replacing the prompt architecture
introducing a new framework
adding web-scraping/headless ChatGPT login
committing secrets
making broad rewrites

## Preferred Task Style

Use small tasks:

Inspect files.
Propose exact changes.
Edit minimal files.
Run compile/test checks.
Summarize results.

Avoid large speculative refactors.

## Current Priority

The near-term roadmap is:

Confirm current bot runs on Linux.
Add/verify LM Studio backend support.
Preserve Ollama/local backend.
Add OpenAI API backend cleanly.
Add lore retrieval plumbing.
Populate curated GFL lore entries.
Improve memory summaries only after the above is stable.
