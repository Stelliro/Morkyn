# AI RPG Consistency Prototype

Version `0.6.0`

AI RPG Consistency Prototype is a local-first browser RPG experiment. A local LLM narrates turns and proposes structured world changes, while SQLite remains the source of truth for the player, inventory, NPCs, events, summaries, and long-running continuity.

It is still pre-1.0 software, but it has enough systems in place to be useful as a playable prototype and a base for experimentation.

## Highlights

- FastAPI backend with a plain browser UI, no frontend build step.
- SQLite world state stored locally under `data/`.
- Local LLM support through llama.cpp-compatible and Ollama-compatible APIs.
- Character and world setup for identity, previous-life details, rules, abilities, economy, magic, tech, skills, progression, and narration style.
- Action-focused turn context so the model reads the relevant facts for movement, combat, ability use, conversation, trade, inventory, training, rest, and investigation.
- Equipment effects that fold equipped item stat modifiers and item-granted abilities into effective player stats/abilities only while equipped.
- Stable entity codes for NPCs, locations, items, and events, with clickable references in narration.
- Visual history, compact memory summaries, source-index search, World Bible view, rewind, regenerate, import, and export.
- Turn generation targets deeper 1000-1500 character prose, short player-input suggestions, and visible elapsed timers during long local-model waits.
- Hidden backend-only GM events for off-screen pressure and delayed consequences.
- Local-only, LAN/phone, and trusted VPN/private-overlay launch modes.

## Requirements

- Windows is the primary supported launch target.
- Python 3.11+ is recommended.
- A local model server or GGUF model is needed for AI generation.
- The app can still open without a configured model, but generation will fall back or fail until model settings are configured.

Install Python dependencies manually when needed:

```powershell
python -m pip install -r requirements.txt
```

## Quick Start

Double-click:

```text
start_ai_rpg.bat
```

Choose one launch mode:

- `1` - This machine only, usually `http://127.0.0.1:8000`
- `2` - Local network / phone on the same Wi-Fi or LAN
- `3` - VPN / virtual network for trusted overlays such as Tailscale, WireGuard, ZeroTier, or OpenVPN

You can also launch non-interactively:

```text
start_ai_rpg.bat local
start_ai_rpg.bat lan
start_ai_rpg.bat vpn 8088
```

The launcher starts the browser app and, when a valid GGUF path is configured, can start a managed llama.cpp server. It also reuses a GGUF path saved in Model Settings on the next launch. Closing the launcher terminal stops managed processes.

## Model Setup

Set a GGUF model path before launching if you want the managed llama.cpp server to start automatically:

```powershell
$env:AI_RPG_GGUF_MODEL="D:\path\to\model.gguf"
```

You can also choose a GGUF path in the app's Model Settings. Pressing **Test Connection** saves the current model fields and, for the `llama.cpp / GGUF` provider, can start a managed llama.cpp server from that GGUF file if nothing is already listening. The launcher will also reuse the saved path on the next launch. Model Settings lets you choose `llama.cpp / GGUF` or `Ollama` explicitly, and exposes a Soft Token Target plus a Hard Token Cap for response generation. If no GGUF path is configured and no Ollama/llama.cpp server is already running, the app opens quickly but gameplay uses deterministic fallback instead of AI generation.

Useful overrides:

```powershell
$env:AI_RPG_LLAMA_CPP_CONTEXT="8192"
$env:AI_RPG_LLAMA_CPP_GPU_LAYERS="-1"
$env:AI_RPG_LLAMA_CPP_FLASH_ATTN="True"
$env:AI_RPG_LLM_STARTUP_TIMEOUT="180"
$env:AI_RPG_MAX_RESPONSE_TOKENS="1500"
$env:AI_RPG_RESPONSE_HARD_CAP_TOKENS="2000"
$env:AI_RPG_MODEL_TRACE_DIR="data/model_traces"
$env:AI_RPG_MODEL_TRACE_KEEP="50"
$env:AI_RPG_TURN_DRAFT_TIMEOUT="900"
$env:AI_RPG_TURN_VERIFY_TIMEOUT="480"
```

Every generated turn writes a local JSON debug trace under `data/model_traces` by default. The trace captures the observable handoff pipeline: focused prompt context, deterministic cleanup stages between handoffs, prompts, raw model outputs, parsed JSON, verifier/self-check output, errors, fallback decisions, and final applied turn data. It cannot include hidden chain-of-thought that the model did not return, but it does include the structured reasoning artifacts the app asks for and receives.

To use an existing local server instead, configure model settings in the UI or set:

```powershell
$env:AI_RPG_MODEL_PROVIDER="llama_cpp"
$env:LLAMA_CPP_BASE_URL="http://127.0.0.1:8080"
```

For Ollama-compatible use:

```powershell
$env:AI_RPG_MODEL_PROVIDER="ollama"
$env:OLLAMA_BASE_URL="http://localhost:11434"
$env:OLLAMA_MODEL="llama3.1"
```

## Playing From A Phone

Use LAN mode when your phone/tablet is on the same trusted Wi-Fi or wired LAN. The launcher prints a recommended phone URL such as `http://192.168.x.x:8000`.

Use VPN mode only on a trusted private overlay. The app UI binds to the selected network, but the managed llama.cpp server stays bound to loopback by default.

If a device times out:

- Use the exact URL printed by the launcher.
- Confirm both devices are on the same LAN or VPN overlay.
- Allow Python or Uvicorn through Windows Firewall for that network profile.

## Runtime Data

Runtime state lives in `data/` and is ignored by git:

- `data/world.db` - SQLite world database
- `data/history_summaries.jsonl` - compact turn summaries
- `data/source_index/` - generated searchable memory index

World export/import uses the `ai-rpg-world-v1` JSON format. Setup settings export/import uses `ai-rpg-setup-settings-v1` and does not include the active world database.

## Development Notes

- The model must return JSON; the backend applies changes conservatively.
- Health, XP, gold, level, inventory counts, and other sensitive values are clamped before persistence.
- Raw journal history is visible to the player, but the model receives structured state, source-index facts, summaries, and bounded hidden GM context instead of full prose history.
- New playthroughs start with no default player skills. Skills emerge through play, training, discovery, or explicit custom proficiency setup rules.
- Equipment-granted abilities are not permanent ability records. They appear in state and prompts only while the source item is equipped.
- The deterministic turn planner packet is versioned separately from the app release version.

More detailed architecture notes live in [CODEBASE_INDEX.md](CODEBASE_INDEX.md), and release history lives in [CHANGELOG.md](CHANGELOG.md).

## License

This project is released for non-commercial use under the PolyForm Noncommercial License 1.0.0. You may edit, fork, and publish modified versions for non-commercial purposes, but commercial use requires separate permission. See [LICENSE.md](LICENSE.md).
