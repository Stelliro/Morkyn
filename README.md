# Mørkyn

<p align="center">
  <img src="Media/morkyn-logo.png" alt="Mørkyn logo" width="68%" />
</p>

**Version `0.8.0`**

**Mørkyn** is a local-first browser RPG. A local LLM narrates turns and proposes structured world changes, while SQLite remains the source of truth for the player, inventory, NPCs, events, summaries, and long-running continuity.

It is still pre-1.0 software, but it has enough systems to be a playable prototype and a solid base for long playthroughs.

## Lore teaser — 100 turns on Mosswake Road

Dual-role stress run (**Player** + **GM** over real `apply_turn` / SQLite, no LLM hang):

| Turns | Errors | Wall time | Mean apply | Final XP | Places |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **100** | **0** | **~4.9 s** | **~45 ms** | 135 | Gate · Alley · Yard · Toll · Clearing |

Story spine and excerpts: **[docs/showcase/100-turn-lore-teaser.md](docs/showcase/100-turn-lore-teaser.md)**  
Metrics JSON: [docs/showcase/100-turn-metrics.json](docs/showcase/100-turn-metrics.json)

```powershell
python benchmarks/run_dual_role_playtest.py
```

<p align="center">
  <img src="Media/morkyn-key-art.png" alt="Mørkyn key art" width="86%" />
</p>

## Interface

| Setup | Play | Model / context health |
| --- | --- | --- |
| <img src="Media/screen-setup.png" alt="Mørkyn setup" width="100%"> | <img src="Media/screen-play.png" alt="Mørkyn play" width="100%"> | <img src="Media/screen-play-model.png" alt="Mørkyn model tab" width="100%"> |

| World setup | LLM settings | Compact mode |
| --- | --- | --- |
| <img src="Media/screen-setup-world.png" alt="Mørkyn world setup" width="100%"> | <img src="Media/screen-model-settings.png" alt="Mørkyn LLM settings" width="100%"> | <img src="Media/screen-play-compact.png" alt="Mørkyn compact mode" width="100%"> |

Assets: [`Media/`](Media/).

## Quick Start

**Requirements:** Windows (primary), Python 3.11+, a local model server or GGUF model (or cloud OpenAI-compatible API).

```powershell
python -m pip install -r requirements.txt
```

Double-click (or run from the repo root):

```text
Morkyn.bat
```

That opens a **simple** pre-play menu. Click a row (or press its number), then **Play**. Prefs save under `data/launcher_prefs.json`.

| Click / key | Action |
| --- | --- |
| **Play** / `1` | Start |
| **Where** / `2` | Cycle local / LAN / VPN |
| **Engine** / `3` | Cycle ollama / llama_cpp / cloud API |
| **Pipeline** / `4` | Toggle narration pipeline |
| **Advanced** / `9` | Full Gatehouse board |
| **Quit** / `0` | Exit |

Skip the menu:

```text
Morkyn.bat local
Morkyn.bat lan
Morkyn.bat vpn 8088
Morkyn.bat play
```

Compatibility shims: `start_ai_rpg.bat` / `start_ai_rpg.ps1` still call `Morkyn.*`.

## Repository layout

```text
Morkyn/
├── Morkyn.bat / Morkyn.ps1   # launcher (keep in root)
├── start_ai_rpg.*            # compatibility shims
├── README.md / CHANGELOG.md / LICENSE.md / PRIVACY_POLICY.md
├── CODEBASE_INDEX.md         # architecture map for contributors / agents
├── requirements.txt
├── .env.example
├── app/                      # FastAPI backend
├── static/                   # browser UI (no build step)
├── Media/                    # logo, key art, screenshots
├── docs/                     # design notes (APIs, pipeline, DSL, metrics)
├── tools/                    # smokes, screenshots, playtest helpers
├── tests/                    # regression + unit tests
├── benchmarks/               # dual-role / long-run harnesses
└── data/                     # local runtime only (gitignored)
```

## Highlights

- FastAPI backend with a plain browser UI (no frontend build step).
- SQLite world state stored locally under `data/`.
- Local LLM support (Ollama / llama.cpp) and optional OpenAI-compatible cloud APIs.
- Character and world setup, action-focused turn context, deterministic NPC combat profiles.
- Hierarchical memory consolidation, token budget guard, campaign save slots.
- Context health panel, compact mode, entity codes, visual history, World Bible, rewind.
- Local-only, LAN/phone, and trusted VPN launch modes.
- Optional adaptive narration pipeline and agent bridge endpoints.

## Privacy

Mørkyn is **local-first**: no analytics, no metrics, no automatic phone-home.

- Policy: [PRIVACY_POLICY.md](PRIVACY_POLICY.md) (also in-app **Privacy** and `/privacy`)
- Optional **Updates** only contact **GitHub** when you check/apply/rollback
- If **uBlock Origin** (or similar) blocks `/static/app.js`, the app shows a blocker notice — allow `127.0.0.1` / localhost for this tab

## Model setup

### Local (GGUF / Ollama)

```powershell
$env:AI_RPG_GGUF_MODEL="D:\path\to\model.gguf"
# or Ollama:
$env:AI_RPG_MODEL_PROVIDER="ollama"
$env:OLLAMA_MODEL="qwen3:8b"
```

### Cloud / agents (xAI Grok, OpenAI, any OpenAI-compatible gateway)

```powershell
$env:AI_RPG_MODEL_PROVIDER="openai"
$env:AI_RPG_API_BASE_URL="https://api.x.ai/v1"
$env:AI_RPG_API_MODEL="grok-4.5"
$env:XAI_API_KEY="xai-..."
```

Or use **LLM Settings** in the UI → provider *Cloud / agent API*. See [docs/ConnectAPIs.md](docs/ConnectAPIs.md).

External agents can drive play via:

```text
POST /api/agent/turn   { "text": "player action" }
GET  /api/agent/state
GET  /api/agent/health
```

Optional lock: `AI_RPG_AGENT_TOKEN`.

Useful overrides:

```powershell
$env:AI_RPG_LLAMA_CPP_CONTEXT="8192"
$env:AI_RPG_LLAMA_CPP_GPU_LAYERS="-1"
$env:AI_RPG_MAX_RESPONSE_TOKENS="1500"
$env:AI_RPG_RESPONSE_HARD_CAP_TOKENS="2000"
$env:AI_RPG_FAST_VERIFICATION="1"
$env:AI_RPG_MEMORY_KEEP_SUMMARIES="12"
$env:AI_RPG_MEMORY_MAX_FACTS="200"
$env:AI_RPG_GM_OFFSCREEN_INTERVAL="8"
```

## Local 8B turn times

Measured on **Ollama `qwen3:8b`** (Q4_K_M, 32k context, thinking off). Times are wall-clock for a full turn pipeline on the machine under test.

| Step | Time |
| --- | ---: |
| Opening scene | ~**1–2 min** (pipeline on; quality pass improved) |
| Typical player turn | ~**1–3.5 min** |
| Dual-role 100-turn backend (no LLM) | ~**5 s** total |

Full tables: [`docs/turn-metrics/`](docs/turn-metrics/). Re-run:

```powershell
python tools/playtest_timed_turns.py
python benchmarks/run_dual_role_playtest.py
```

## Debug (per turn)

Each completed turn has a collapsed **Debug** row under the narration:

| Action | What it does |
| --- | --- |
| Click **Debug** | Expand / collapse summary (check status, usage phases, path) |
| **Copy summary** | Clipboard: short human-readable dump |
| **Copy JSON** | Clipboard: structured debug bundle |
| **Copy path** | Clipboard: local `data/model_traces/…` path |
| **View file** | Loads the full trace JSON in-panel via `/api/debug-trace` |

Trace files are written under `data/model_traces/` (gitignored). The play view stays clean until you expand a turn.

## Development

```powershell
python tests/behavior_test.py
python tests/test_narration_pipeline.py
python benchmarks/run_dual_role_playtest.py
```

## Docs and license

| Doc | Link |
| --- | --- |
| Architecture | [CODEBASE_INDEX.md](CODEBASE_INDEX.md) |
| Docs index | [docs/README.md](docs/README.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Privacy | [PRIVACY_POLICY.md](PRIVACY_POLICY.md) |
| License | [LICENSE.md](LICENSE.md) (PolyForm Noncommercial 1.0.0) |

| Field | Value |
| --- | --- |
| Product | **Mørkyn** |
| Version | **0.7.0** |
| GitHub | https://github.com/Stelliro/Morkyn |

Formerly published as AI RPG Consistency Prototype (`ai-rpg-consistency-prototype`).
