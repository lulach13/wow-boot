# WoW Patch Bot

A Discord bot for a WoW guild. Members register their character, and when a new
patch or hotfix drops the bot pulls together the official notes plus community
coverage (Wowhead, Icy Veins), runs it through a local LLM, and DMs each person a
short "here's what actually changed for *your* spec" summary. There's also a
retrieval knowledge base so those class guides can be queried instead of
re-scraped every time.

I built it because our guild chat turns into the same conversation every patch
day — someone links the patch notes, then fifteen people ask "ok but did
anything change for X". This automates the annoying part: everyone gets a
tailored answer in their DMs based on the class/spec they registered.

## What it actually does

- **Character registration** via slash commands with proper Discord select-menu
  UI (`/register`, `/profile`, `/unregister`). Class -> spec -> content focus,
  stored in SQLite. Role (tank/healer/dps) is inferred from the spec.
- **Patch detection**: on an interval it scrapes the Blizzard WoW news page for
  articles matching patch/hotfix keywords, and stores new ones.
- **Per-player analysis**: for each registered user it grabs Icy Veins class
  updates for their spec, hands the official notes + community text to a local
  Ollama model, and DMs back a concise, spec-specific breakdown.
- **Armory lookups** through the Battle.net API (`services/armory.py`) — pulls
  class, spec, faction, item level for a character.
- **Stat-priority comparison** (`/compare_stats`): scrapes both Icy Veins and
  Wowhead and flags when the two sources disagree on stat order. This one's
  genuinely handy — the sites drift apart after balance changes.
- **Knowledge base** (`services/knowledge_base/`): scrapes guide pages, chunks
  them, embeds with sentence-transformers, and stores in ChromaDB so guide
  content is retrievable by class+spec. Re-indexed nightly.

Most of the admin commands (`/check_patches`, `/check_updates`,
`/update_knowledge_base`, `/check_registered`) are gated behind the
administrator permission — they're the manual triggers I use while testing.

## How it's put together

```
bot/            Discord layer — the bot entrypoint and the cogs (slash commands)
  cogs/         registration, notifications, knowledge_base
services/       the actual work
  blizzard_api  Battle.net OAuth + character + patch-note fetching
  armory        maps the raw API payload into a CharacterProfile
  scrapers/     icy_veins + wowhead parsers
  llm           talks to Ollama, builds the analysis prompt
  scheduler     apscheduler jobs: poll patches, run analysis, DM users
  knowledge_base RAG: chunk -> embed -> ChromaDB -> retrieve
db/             SQLAlchemy models + session helper
config.py       pydantic-settings, reads from .env
```

The LLM step runs against **Ollama locally** rather than a paid API — it's a
guild side-project, so keeping inference free and offline mattered more than
squeezing out the best possible summaries. Swapping it for a hosted model would
just mean changing `services/llm.py`.

## Setup

You'll need Python 3.11+, a running [Ollama](https://ollama.com/) with a model
pulled (default is `llama3.1`), a Discord bot token, and Battle.net API
credentials from https://develop.battle.net/.

```
pip install -r requirements.txt
cp .env.example .env   # then fill it in
python -m bot.main
```

The `.env` values:

| var | what it is |
| --- | --- |
| `DISCORD_TOKEN` | your bot token |
| `DISCORD_GUILD_ID` | the server the slash commands sync to |
| `DISCORD_PATCH_CHANNEL_ID` | channel used by the `/check_registered` roster dump |
| `BLIZZARD_CLIENT_ID` / `BLIZZARD_CLIENT_SECRET` | Battle.net API app creds |
| `BLIZZARD_REGION` | `us` / `eu` / etc. |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | your local Ollama endpoint + model |
| `PATCH_CHECK_INTERVAL_MINUTES` | how often to poll for patches |

`.env` is gitignored. Don't commit real tokens.

## Tests

```
pip install pytest pytest-asyncio
pytest
```

The suite covers the pure logic that's worth protecting: the Armory
payload -> `CharacterProfile` mapping (including the spec->role inference and
missing-field fallbacks), the guide-text chunker, and the Icy Veins / Wowhead
scrapers. The scraper tests run against **saved HTML fixtures** under
`tests/fixtures/` rather than hitting the live sites — that keeps them fast and
deterministic, and it's exactly the layer that breaks when a site changes its
markup, so it's the layer worth asserting on. The Discord and Ollama calls
aren't unit-tested; they're thin I/O wrappers and I'd only be asserting against
my own mocks.

## Known limitations / rough edges

- The scrapers depend on the current HTML of Blizzard news, Wowhead, and Icy
  Veins. When any of them reworks their markup, the relevant selector needs
  updating — the fixtures make that quick to catch but it's still manual.
- Slash commands sync to a single guild (`DISCORD_GUILD_ID`), so this is really
  built for one server, not a public multi-guild bot.
- `services/armory.py` can fetch item level, but the registration flow doesn't
  currently backfill `armory_ilvl` on the stored user — the column exists and
  the roster embed will show it if populated, I just haven't wired the two
  together yet.
- `tools.py` is a leftover stub from an earlier direction and isn't imported by
  anything. Left it in rather than pretend the repo was built in one clean pass.
- Summaries are only as good as the local model you point it at. `llama3.1` is
  fine; a 1b model is noticeably worse.
