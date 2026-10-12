# Mørkyn

<p align="center">
  <img src="Media/morkyn-cover.png" alt="Mørkyn: the model narrates, the game decides what is true" width="72%" />
</p>

**Version `0.10.0-dev.8`** · pre-release builds on the way to `0.10.0`, not stable (see [CHANGELOG](CHANGELOG.md) for each `dev.N`). Last stable: [`0.9.12`](https://github.com/Stelliro/Morkyn/releases/tag/v0.9.12). Previous stable: [`0.9.0`](https://github.com/Stelliro/Morkyn/releases/tag/v0.9.0).

## This is not the usual AI RPG

Most "AI RPGs" are a chat window with a system prompt. The model is the whole game: it remembers what fits in its context, rolls whatever number sounds right, and quietly rewrites your inventory, your location, and the people you met once the early turns scroll away. Play long enough and the world you were in is gone.

Mørkyn turns that around. **The model only narrates. The engine decides.**

- **The world is a database, not a transcript.** Player, places, people, items, quests, relationships, and the private motives of NPCs live in SQLite. The model proposes changes in a closed op language; the engine applies what is justified and refuses the rest. A gain the ops claim but the prose never shows arriving is refused; a pickup the prose shows and the ops forgot is granted, so the story and the inventory cannot drift apart.
- **Every number is rolled by the server.** The model writes a band such as `small` or `huge`; the app rolls the amount, scales it by level and difficulty, and writes every roll to an audit table you can read.
- **Continuity is a contract, not a hope.** Where you are, what you are called, who an NPC is, what the world already told you, the dice that already fell: each is stated to the model every turn and verified after. When the prose dodges a name it owes you, the engine says the name.
- **Rewind really rewinds.** Regenerate a turn and the same dice fall, the same encounter rolls, the same clocks tick, and nothing the discarded turn wrote survives.
- **It runs at home on a 7B.** Local-first, nothing leaves your machine. A small model is enough because it never has to be the memory, the referee, or the map.

It is pre-1.0 software, but it is a playable prototype with enough systems under it for long playthroughs. The claims above are tested behaviours, not lines in a prompt.

## Download

This drop is **[`v0.9.12`](https://github.com/Stelliro/Morkyn/releases/tag/v0.9.12)**. One file, empty folder, run it. The launcher clones the repo, builds a private `.venv`, installs dependencies, and starts the game.

| OS | File | Download |
| --- | --- | --- |
| **Windows** | `start.bat` | **[Download start.bat](https://github.com/Stelliro/Morkyn/releases/download/v0.9.12/start.bat)** — double-click |
| **Linux** | `start.sh` | **[Download start.sh](https://github.com/Stelliro/Morkyn/releases/download/v0.9.12/start.sh)** — `bash start.sh` |
| **macOS** | `start.sh` | **[Download start.sh](https://github.com/Stelliro/Morkyn/releases/download/v0.9.12/start.sh)** — same script as Linux |

Release page (notes + both files): [**Mørkyn 0.9.12**](https://github.com/Stelliro/Morkyn/releases/tag/v0.9.12)

```text
Windows        double-click start.bat
Linux / macOS  bash start.sh
```

Later runs check GitHub and **ask before updating** — answer no and it starts the copy you already have. Offline, it skips the check. It never touches a checkout with uncommitted local changes.

| Flag | Effect |
| --- | --- |
| `--full` | also install `llama-cpp-python` (only for the built-in GGUF server) |
| `--update` | apply an available update without asking |
| `--no-update` | skip the update check entirely |
| `--help` | full usage |

Both scripts also work from inside an existing checkout — they detect it and skip the clone. Requires Git and Python 3.11+.

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

## Interface

| Main menu | Play | Quests |
| --- | --- | --- |
| <img src="Media/screen-menu.png" alt="Mørkyn main menu" width="100%"> | <img src="Media/screen-play.png" alt="Mørkyn play view with scene and map" width="100%"> | <img src="Media/screen-play-quests.png" alt="Mørkyn quest log" width="100%"> |

| New game setup | LLM settings | Play menu |
| --- | --- | --- |
| <img src="Media/screen-setup.png" alt="Mørkyn new game setup" width="100%"> | <img src="Media/screen-model-settings.png" alt="Mørkyn LLM settings" width="100%"> | <img src="Media/screen-play-menu.png" alt="Mørkyn play menu" width="100%"> |

| Town streets | Town close-up |
| --- | --- |
| <img src="Media/screen-town.png" alt="Mørkyn town view with roads, plots and shops" width="100%"> | <img src="Media/screen-town-closeup.png" alt="Mørkyn town map close-up" width="100%"> |

Assets: [`Media/`](Media/).

## Already have the repo

```powershell
python -m pip install -r requirements.txt
```

Double-click (or run from the repo root):

```text
Morkyn.bat
```

Mørkyn opens in **its own window**: no tabs, no address bar, no terminal left open behind it. The window shows the startup log while the server starts, then the main menu. Closing the window stops the server and any managed llama.cpp server.

The terminal launcher's settings now live in the game:

| Where | What |
| --- | --- |
| **Main menu → Gatehouse** | **Where** (this PC / LAN / VPN), **Engine** (MLE / llama.cpp / cloud API), **Pipeline** (the paragraph writer, off by default: the draft's own prose ships, see *Local turn times*). Saves as you pick. The line under it is the address phones and other PCs use. |
| **Settings** | Everything else the old Advanced board had: port, model and GGUF path, API base and model, context and response tokens, llama.cpp GPU layers / flash attention / log / startup wait, draft format, consolidator, fast verification, skip the DSL verifier, theme, and where the game opens (Mørkyn window, system browser, or server only). **Restore defaults** fills the form with the defaults. |

Most settings apply at once. Where, port, and the llama.cpp server settings need the server to start again; Settings and the main menu say so and offer **Restart now**, and the window comes back by itself (on the new port, if that changed). If the server cannot start (a port in use, a missing GGUF file), the window says why and lets you fix Where, port, engine, or GGUF path and retry. Logs are in `data/logs/` (`launcher.log`, `server.log`). Prefs save under `data/launcher_prefs.json`.

It is still a website. While Mørkyn runs, any browser on this PC can open `http://127.0.0.1:8000/`, and phones or other PCs can use the address on the main menu when Where is LAN or VPN. Pop-out (↗) on a tab opens a separate window: a real window of its own inside Mørkyn's app, a browser popup in a normal browser.

Start options (the same words the old launcher took):

```text
Morkyn.bat local
Morkyn.bat lan
Morkyn.bat vpn 8088
Morkyn.bat --browser     open the game in the system browser
Morkyn.bat --console     no window: run in the terminal, Ctrl+C stops (also works on Linux: python morkyn_app.py --console)
```

The window uses [pywebview](https://pywebview.flowheater.net/) with the system WebView2; `Morkyn.bat` installs it the first time. Without it, Mørkyn runs in the terminal and opens your browser. The old terminal menu is still there: `powershell -File Morkyn.ps1`.

Compatibility shims: `start_ai_rpg.bat` / `start_ai_rpg.ps1` still call `Morkyn.*`.

## Repository layout

```text
Morkyn/
├── start.bat / start.sh      # one-file launchers (Windows / Linux+macOS) — also GitHub release assets
├── Morkyn.bat                # in-repo launcher (keep in root): opens morkyn_app.py
├── morkyn_app.py             # Mørkyn's own window; starts and restarts the server (app/launcher.py)
├── Morkyn.ps1                # the old terminal Gatehouse menu, still usable
├── start_ai_rpg.*            # compatibility shims
├── README.md / LICENSE.md / PRIVACY_POLICY.md
├── CHANGELOGS.md             # index: per-version notes, devlogs, full log
├── CHANGELOG.md              # the full line-by-line change log
├── changelogs/               # notes per version; devlogs/ holds GitHub and itch.io devlogs
├── CODEBASE_INDEX.md         # architecture map for contributors / agents
├── requirements.txt
├── .env.example
├── app/                      # FastAPI backend
├── static/                   # browser UI (no build step; see docs/UI_RULEBOOK.md)
├── Media/                    # logo, key art, screenshots
├── content/                  # built-in content packs
├── docs/                     # design notes (APIs, pipeline, DSL, metrics)
├── tools/                    # smokes, screenshots, playtest helpers
├── tests/                    # regression + unit tests
├── benchmarks/               # dual-role / long-run harnesses
└── data/                     # local runtime only (gitignored)
```

## MLE — the Mørkyn Large Language Model Engine

MLE is the layer between the language model and the game. It covers what the model is told, what it may answer with, and what the game engine does with the answer. `app/mle.py` is the part that runs a local model. The contract below is the same whether the model is MLE, llama.cpp or a cloud API.

The rule: **the LLM writes words. The engine owns every fact and every number.**

### What the LLM does, and what it does not

| | **The LLM** | **The game engine** |
| --- | --- | --- |
| **The scene** | **Writes the prose**: what you see, what people say and do | Trims what breaks the rules: acting or speaking for you, repeating a line, using a name nobody told it |
| **People** | **Gives NPCs their voice** | Decides who you are talking to and who answers, before the model is asked |
| **Changes to the world** | **Proposes them** as short op lines (`GRANT`, `MOVE`, `GOLD`, `TALK` ...) | Applies them or refuses them, against the save and the prose |
| **Amounts** | **Names a size**: `small`, `moderate`, `large` | Rolls the number on the server, seeded, logged in `dice_rolls` |
| **Skill checks** | **Narrates the result** it is handed | Rolls the d20 before the draft and writes the outcome |
| **Quests** | **Offers work** in the story; a second call reads that offer back as data | Decides whether it becomes a quest, tracks the steps, pays the reward |
| **Abilities** | **Names and describes** a power; picks a growth template and a seed in words | Computes every number: ranks, XP per use, caps, cost |
| **Memory** | Sees only the packet it is sent | Keeps the whole world in SQLite and picks what each call needs |

In one turn the LLM is called for at most four jobs:

1. **Draft**: always. It writes the scene and its op lines.
2. **Verify**: only when a fixed certainty score says the draft is risky. The answer is *pass* or *revise* plus a small patch.
3. **Repair**: only when a check fails, such as thin prose, a dodged answer or the wrong voice. It asks for prose only.
4. **Quest parse**: only when the finished scene looks like it offers work.

### The LLM never writes code

Its output is only ever prose and data:

- **Closed ops.** Changes come back as lines from a closed set of about thirty ops ([docs/TurnDsl.md](docs/TurnDsl.md)). A fixed transcoder (`app/turn_dsl.py`) turns them into a turn record, and an unknown op is refused.
- **Nothing is executed.** There is no `eval` and no `exec`. No SQL is built from model text; values are bound as parameters.
- **Escaped on screen.** The narration is HTML-escaped before the browser shows it.
- **Fallbacks are data too.** If the ops cannot be parsed, the fallback is a JSON draft: plain data, checked the same way.

### One turn, step by step

1. **The engine reads your line first.** It does all of this before the model sees anything:
   - It removes out-of-character notes and decides who you are talking to (`app/conversation.py`).
   - It records what you are in the middle of (`app/scene_thread.py`).
   - It matches a power you used and charges its cost, advances the clock and spends energy.
   - It rolls your skill checks with seeded dice (`app/skill_checks.py`).
2. **The engine builds the context.** `build_prompt_context` scores what this turn needs: the people here, the place, open quests, items, skills, world facts and the last scene. It adds the decisions from step 1 and the contracts the prose must keep. The model gets a focused packet, not the save.
3. **The LLM drafts** the scene as prose plus op lines. Every later call in the turn reuses the same system prompt, so a local model keeps its cache.
4. **The draft is checked.** The verifier and repairs run if needed, then fixed trims remove anything the narrator did for you.
5. **The engine applies what holds up** (`apply_turn`):
   - Gains need the prose to show them arriving. Moves are checked against the map and the roads.
   - Every amount is rolled ([docs/DiceAuthority.md](docs/DiceAuthority.md)). A price the prose names is the price paid.
   - Quest offers are judged, and rewards are paid by the engine.
6. **The engine keeps the record**: rewind snapshots, relationships and memory consolidation, with no model call.

If the model fails, the turn stops with a dialog that says why, or it falls back to a plain engine turn. The world is never left half-written.

### Example: one real turn

This is a turn from a copy of a live save, played on Qwen3 8B (Q4) on a 12 GB card on 2026-10-12. It is cut for length: some packet fields and op lines are left out and quotes are straightened, but the words are the model's own. It also shows four open bugs, which are explained at the end.

**1. The player types**

```text
I set the last polished blade on the rack and ask Finnian if he'd sell me a whetstone. I'll pay 2 gold for it.
```

**2. The engine decides, before the LLM is called**

```text
talking to    Finnian [C], named in the player's line. Only Finnian answers.
doing         quest Q1 "Polish swords", still under way; this action happens inside it
skill check   Persuasion  d20 = 10  vs DC 7  ->  success   (server roll, seeded, dice_rolls #81)
energy        talk, costs 0
trade offer   the player offers 2 gold
```

**3. What the LLM is sent** (an excerpt of a 13 KB packet, plus a 19 KB system prompt with the op list and prose rules)

```json
{
  "player_line": "I set the last polished blade on the rack and ask Finnian if he'd sell me a whetstone. I'll pay 2 gold for it.",
  "trade_offer": {"gold": 2},
  "world_state": {
    "current_location": {"name": "Lucky Heron Armory", "code": "L3", "keeper": "Finnian",
      "people": [{"name": "Finnian", "code": "C", "role": "armorer",
        "already_said": ["Not bad, not bad at all. We could use someone like you around here.",
                         "If you're interested, I might have a little job for you. Something to help you get started."]}]},
    "conversation_turn": {"talking_to": [{"name": "Finnian", "code": "C"}], "answers": "talking_to only"},
    "mechanics_context": {"resolved_checks": [{"skill": "persuasion", "outcome": "success"}]},
    "active_quests": [{"code": "Q1", "title": "Polish swords", "now": "Start by helping Finnian polish these swords"}]
  },
  "output_contract": {"format": "nar_ops_v0", "required_sections": ["===NAR===", "===OPS==="]},
  "instructions": [
    "player_line is the player's whole turn. ... the player's further actions, words, thoughts, feelings and decisions are theirs to write, not yours.",
    "trade_offer: the player offers 2 gold. If the other side accepts, ===OPS=== has GOLD -2 and ===NAR=== shows the coin handed over ..."
  ]
}
```

**4. What the LLM writes back** (the draft call, 15.1 s, raw)

```text
===NAR===
You set the last polished blade on the rack and ask Finnian if he'd sell you a whetstone. He looks up from his bench, wiping his hands on a cloth, and gives you a slow nod. "A whetstone, you say? I've got one just the right size for your blade," he says, reaching into a drawer behind him. "It's a little pricey, though. Two gold for it."

You pull out two gold coins from your pouch and hand them over. Finnian takes the coins with a grunt, then pulls out a rough-hewn stone the size of your palm. "This'll keep your blade sharp for a while," he says, handing it to you. "You'll need it if you're planning on doing any real fighting."

You nod, tucking the whetstone into your satchel. Finnian's eyes flicker to the rack of polished blades, and a faint smile plays on his lips. "You're doing good, Alaric," he says. "I've got a little job for you if you're interested. Something to help you get started."

===OPS===
GRANT "whetstone" QTY moderate TYPE stone DESC "a rough-hewn stone the size of your palm" RARITY uncommon
GOLD -2
TALK C "a little job to help you get started"
SUMMARY "Finnian offers a job to help Alaric get started"
QUEST "Learn more about sword polishing" GIVER C STEP "Learn more about sword polishing" AT L3
```

The LLM made two more calls. The verifier answered `{"verdict": "pass", "issues": [], "patch": {}}` in 4.1 s. The quest parser read the scene back as JSON, a new offer plus two "step done" marks, in 15.8 s.

**5. What the engine did with it**

```text
prose     cut  "You pull out two gold coins from your pouch and hand them over."   (acting for the player)
          cut  "You nod, tucking the whetstone into your satchel."                  (acting for the player)
          cut  "I've got a little job for you if you're interested. ..."            (Finnian already said it)
          cut  ", Alaric" from "You're doing good, Alaric"                          (Finnian was never told the name)
          link Finnian -> [[C]]
dice      whetstone count: band "moderate" -> rolled 2                              (dice_rolls #80)
items     whetstone x2 REFUSED: the final prose does not show it arriving
gold      GOLD -2 voided: nothing changed hands
quests    new "Learn more about sword polishing" REFUSED: duplicate of Q2
          Q1 "Polish swords" complete: +11 gold, +27 XP, paid by the engine
          Q2 "Learn metalworking" complete: +11 gold, +27 XP, paid by the engine
result    gold 12 -> 34, inventory unchanged, 35.7 s for the whole turn
```

**Where this turn went wrong.** Every decision above was made by the engine. Four of them were wrong, and they are logged as open issues:

- **#96.** The whetstone was refused although the prose hands it over ("handing it to you").
- **#97.** The trim cut the coins the player offered, so "Finnian takes the coins" is left with no coins given. The draft had followed its own instruction (`trade_offer`), and the trim rule disagrees with it.
- **#98.** One action finished two quests.
- **#99.** "A whetstone" rolled a count of 2.

See [docs/PLAYTEST_ISSUES.md](docs/PLAYTEST_ISSUES.md).

### Setup works the same way

The LLM proposes and the engine settles. For abilities:

- The LLM picks a growth template and a seed in words, such as *slow / ordinary / range grows*.
- `app/ability_growth.py` computes the rank ladder, XP per use (scaled by risk), soft caps and walls.
- The LLM starts from a theme library (`app/ability_library.py`, 204 templates over 17 themes). A new power it invents is checked, stored, and offered in later games.

Gear stats, eye colour, map placement and town layout are rolled by the engine in the same way.

### The local runtime (`app/mle.py`)

- **In-process model.** One GGUF loads inside the game through llama-cpp-python, so no separate server is needed. The context size fits your free VRAM, and a missing file says so instead of answering.
- **Word masking.** While drafting, it can hide an overused word at the moment the next token is chosen. Names, titles and op keys always stay choosable, and stray CJK script tokens are masked.
- **Nothing rewritten.** The weights file is never changed, and the model's text is not edited by the runtime. All cuts happen afterwards, in the engine, and are logged.

Further reading: [docs/NarrationPipeline.md](docs/NarrationPipeline.md) · [docs/TurnDsl.md](docs/TurnDsl.md) · [docs/DiceAuthority.md](docs/DiceAuthority.md) · [docs/SkillChecks.md](docs/SkillChecks.md) · [CODEBASE_INDEX.md](CODEBASE_INDEX.md)

## Highlights

- FastAPI backend with a plain browser UI (no frontend build step).
- SQLite world state stored locally under `data/`.
- Local LLM support (MLE / llama.cpp) and optional OpenAI-compatible cloud APIs.
- Character and world setup, action-focused turn context, deterministic NPC combat profiles.
- Hierarchical memory consolidation, token budget guard, campaign save slots.
- Context health panel, compact mode, entity codes, visual history, World Bible, rewind.
- Local-only, LAN/phone, and trusted VPN launch modes.
- Optional adaptive narration pipeline and agent bridge endpoints.
- Optional **local character art** via Forge / A1111 (primary) — ComfyUI hooks exist but are **not fully verified yet**.
- Optional **read aloud**: the narration spoken paragraph by paragraph by a local CPU engine (Piper) or a speech API (OpenAI-compatible, ElevenLabs). Off by default — [docs/TextToSpeech.md](docs/TextToSpeech.md).

### Latest

- **0.10.0 dev builds:** Mørkyn's own window, abilities whose growth the engine computes, a theme ability library that learns new powers, death and Ironman, towns with streets, read-aloud narration. Full notes: [changelogs/0.10.0-dev.md](changelogs/0.10.0-dev.md).
- **Newest devlog:** [Its own window, and powers that grow](changelogs/devlogs/itch-0.10.0-dev.9.md).

Every version, every devlog and the full change log: **[CHANGELOGS.md](CHANGELOGS.md)**.

## Local images (ForgeSD / ComfyUI)

Optional portraits and full-body art use a **local** image backend. Nothing runs until you set a provider in **LLM Settings → Images**.

| Backend | Status in Mørkyn |
| --- | --- |
| **Forge / ForgeSD** | **Supported path** — actively used and tested |
| **ComfyUI** | **Wired but unverified** — config tabs + launch/helpers exist; end-to-end generation has **not** been fully signed off by the project owner yet. It will be marked verified once the owner or a contributor confirms it. |

Docs: [docs/ConnectImages.md](docs/ConnectImages.md) · [docs/CharacterPortrait.md](docs/CharacterPortrait.md)

Repos / face-lock extras (InstantID, FaceID, IPAdapter Plus, InsightFace wheel) are listed under **LLM Settings → Images → Installs**. Install buttons stay **blocked** until the matching Forge or Comfy install root is set; already-present pieces show **Installed**.

## Privacy

Mørkyn is **local-first**: no analytics, no metrics, no automatic phone-home.

- Policy: [PRIVACY_POLICY.md](PRIVACY_POLICY.md) (also in-app **Privacy** and `/privacy`)
- Optional **Updates** only contact **GitHub** when you check/apply/rollback
- If **uBlock Origin** (or similar) blocks `/static/app.js`, the app shows a blocker notice — allow `127.0.0.1` / localhost for this tab

## Model setup

### Local (GGUF / MLE)

```powershell
$env:AI_RPG_GGUF_MODEL="D:\path\to\model.gguf"
# or MLE:
$env:AI_RPG_MODEL_PROVIDER="mle"
$env:MLE_MODEL="qwen3:8b"
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
$env:AI_RPG_LLAMA_CPP_CONTEXT="32768"   # explicit override; leave the launcher pref on "auto" to size it from the model's header and your GPU
$env:AI_RPG_LLAMA_CPP_GPU_LAYERS="-1"
$env:AI_RPG_MAX_RESPONSE_TOKENS="1500"
$env:AI_RPG_RESPONSE_HARD_CAP_TOKENS="2000"
$env:AI_RPG_FAST_VERIFICATION="1"
$env:AI_RPG_MEMORY_KEEP_SUMMARIES="12"
$env:AI_RPG_MEMORY_MAX_FACTS="200"
$env:AI_RPG_GM_OFFSCREEN_INTERVAL="8"
$env:AI_RPG_TTS_PROVIDER="piper"        # read aloud: off (default) | piper | openai | elevenlabs
$env:AI_RPG_TTS_ENABLED="1"
$env:AI_RPG_TTS_API_KEY="..."           # speech API key; falls back to OPENAI_API_KEY / ELEVENLABS_API_KEY
```

The full `AI_RPG_TTS_*` list (preset, voice, model, base URL, speed, chunk size, timeout, voice folder) is in [`.env.example`](.env.example) and [docs/TextToSpeech.md](docs/TextToSpeech.md).

## Local turn times

Two measurements so far, both through MLE (the in-process engine) on the same 12 GB GPU with the launcher's `auto` context. A full timed playtest of `0.10.0-dev.7` has not been run yet; the numbers below are what has actually been measured.

**Qwen2.5 7B Instruct (Q4_K_M), the default launcher setup.** A real hand-played game on `0.10.0-dev.7`, 7 October 2026: an opening and 12 player turns, paragraph writer off (the default). Times are from the first to the last step in each turn's trace (`data/model_traces`), so the browser round trip is not included.

| Step | Time |
| --- | ---: |
| Opening scene | **13 s** |
| Player turn, median | **8 s** |
| Player turns, range | 3-17 s |
| Turns where the fact-check ran (3 of 12) | 8-17 s |

The launcher's default model name is `qwen3:8b`; when `data/mle-models` holds a single GGUF, MLE loads that file under the default name, which here is Qwen2.5 7B. To run Qwen3 8B, put its GGUF there (or set the MLE model to its path).

**Qwen3 8B (Q4_K_M).** October 2026 live A/B: two scripted games, five turns each, context `auto` (24,576 tokens on that GPU).

| Step | Paragraph writer off (default) | Paragraph writer on |
| --- | ---: | ---: |
| Opening scene | ~**30 s** | ~**38 s** |
| Typical player turn | ~**18 s** | ~**32 s** |
| Dual-role 100-turn backend (no LLM) | ~**5 s** total | |

A blind score of the same games found 3 restated sentences with the writer off against 18 with it on, and better readability; the writer is kept as a launcher toggle. Turns where the fact-check runs take longer (up to ~50 s).

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
python -m unittest discover -s tests -p "test_*.py"   # the full suite
python tests/behavior_test.py                          # memory / token / slot checks
python benchmarks/run_dual_role_playtest.py            # 100 turns over the real engine, no model
```

Playtest findings and their status are tracked in [`docs/PLAYTEST_ISSUES.md`](docs/PLAYTEST_ISSUES.md). A staged live playtest (settings, people, relationships, fighting, items, map, skills, factions, magic, save/reload) runs on the local 8B in a temp data dir as a Claude Code workflow: `.claude/workflows/staged-playtest.js`. Every stage must report evidence before it counts as passed.

## Docs and license

| Doc | Link |
| --- | --- |
| Architecture | [CODEBASE_INDEX.md](CODEBASE_INDEX.md) |
| Docs index | [docs/README.md](docs/README.md) |
| Changelogs and devlogs | [CHANGELOGS.md](CHANGELOGS.md) |
| Full change log | [CHANGELOG.md](CHANGELOG.md) |
| Privacy | [PRIVACY_POLICY.md](PRIVACY_POLICY.md) |
| License | [LICENSE.md](LICENSE.md) (PolyForm Noncommercial 1.0.0) |

| Field | Value |
| --- | --- |
| Product | **Mørkyn** |
| Version | **0.10.0-dev.8** |
| GitHub | https://github.com/Stelliro/Morkyn |

Formerly published as AI RPG Consistency Prototype (`ai-rpg-consistency-prototype`).
