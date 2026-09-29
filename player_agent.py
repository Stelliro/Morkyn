"""
player_agent.py — Autonomous two-role playtest loop for Mørkyn
==============================================================
Runs from the project root:
    python player_agent.py [--turns 120] [--ollama-url URL] [--port PORT] [--keep-db]

Architecture
------------
One Ollama model plays BOTH roles:

  Game role:   Morkyn's own narrative engine (uvicorn subprocess on a free port).
               The model generates the in-world response to each player action.

  Player role: A direct Ollama chat call with a "you are the player" system prompt.
               Reads the game's narration + state and returns the next player action.

Loop
----
1. Start uvicorn subprocess (Morkyn server)
2. Poll /api/version until ready (up to 60 s)
3. POST /api/model-config   → tell Morkyn which Ollama model to use
4. POST /api/setup          → start a fresh playthrough with an opening scene
5. For each turn (default 120):
   a. GET /api/state         → grab current player stats
   b. Send last narration + stats to Ollama as the player brain → get next action
   c. POST /api/turn         → send that action to Morkyn
   d. Extract narration from response
   e. Check for bugs (empty response, JSON errors, character breaks, repetition)
   f. Log everything; continue on error (don't abort)
6. Kill the uvicorn subprocess
7. Write player_agent_report.txt
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_TURNS = 120
SERVER_STARTUP_TIMEOUT = 90      # seconds to wait for uvicorn to become ready
TURN_HTTP_TIMEOUT = 180          # seconds per /api/turn call (LLM can be slow)
PLAYER_BRAIN_TIMEOUT = 60        # seconds for Ollama player-brain call
REPETITION_WINDOW = 5            # recent narrations to check overlap against
REPETITION_THRESHOLD = 0.75      # word-overlap fraction that flags repetition

PLAYER_BRAIN_SYSTEM = """\
You are an engaged player in a text-based RPG. You will receive the current game \
narrative, your character's stats, and a summary of what you know so far. \
Respond with ONLY the player's next action as a short command (1–2 sentences max).

Rules:
- Stay in character — write what YOUR CHARACTER does, not what "the player" does.
- Be curious and active: explore, fight enemies when you encounter them, pick up \
items, talk to NPCs, accept quests, equip better gear, trade at shops, use abilities.
- Vary your actions. Never repeat the exact same action twice in a row.
- No meta-commentary. No "I think I should…" Just the action itself.
- Keep it short: one or two sentences only.
- NEVER use debug commands. Any input starting with /, !, or DEBUG is forbidden. \
You are playing as a real character, not a tester.
- Your goal: become as powerful as possible. Seek out combat to gain experience, \
find better weapons and armor and equip them, make allies with useful NPCs, and try \
to assemble a party of companions to travel with. Be proactive — don't wait, \
explore and push forward.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Lore Bible / Entity Tracker
# ──────────────────────────────────────────────────────────────────────────────

# Common English words and fantasy filler to exclude from proper-noun detection
_COMMON_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "of", "for",
    "with", "by", "from", "as", "is", "was", "are", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "shall", "can", "not", "no", "nor", "so", "yet", "both",
    "either", "neither", "if", "then", "that", "this", "these", "those", "it",
    "its", "he", "she", "they", "them", "their", "you", "your", "we", "our",
    "my", "me", "him", "her", "his", "who", "which", "what", "where", "when",
    "how", "all", "any", "each", "every", "more", "most", "such", "than", "there",
    "here", "just", "also", "very", "too", "up", "out", "now", "only", "over",
    "after", "before", "into", "through", "around", "upon", "about", "against",
    "between", "during", "without", "within", "along", "toward", "behind", "above",
    "below", "near", "among", "across", "down", "off", "while", "though", "until",
    "since", "once", "still", "back", "away", "again", "already", "never",
    # Common RPG/fantasy words that look like proper nouns
    "North", "South", "East", "West", "Inn", "Tavern", "Town", "Village",
    "Road", "Street", "Gate", "Keep", "Tower", "Cave", "Forest", "River",
    "Dark", "Light", "Shadow", "Fire", "Blood", "Iron", "Stone", "Old",
    "New", "Great", "High", "Low", "Long", "Far", "Deep", "Beyond",
    "Lord", "Lady", "King", "Queen", "Sir", "The", "One", "Two", "Three",
    "Day", "Night", "Morning", "Evening", "Winter", "Summer", "Spring", "Autumn",
    # Capitalized sentence-start words often aren't proper nouns — heuristic only
    "You", "Your", "He", "She", "It", "They", "We", "His", "Her", "Their",
    "As", "At", "In", "On", "To", "Of", "By", "With", "From", "For", "But",
    "And", "Or", "If", "When", "Where", "While", "After", "Before", "Though",
    "Then", "So", "Yet", "Both", "Each", "Every", "Some", "Any", "All",
    "That", "This", "These", "Those", "What", "Who", "How", "There", "Here",
})

# Patterns to help classify entities
_ITEM_KEYWORDS = re.compile(
    r"\b(sword|blade|axe|bow|staff|dagger|mace|shield|helm|helmet|armor|armour"
    r"|cloak|ring|amulet|talisman|tome|scroll|potion|wand|spear|lance|hammer"
    r"|gloves|boots|greaves|gauntlets|vest|robe|mail|plate)\b",
    re.IGNORECASE,
)
_PLACE_KEYWORDS = re.compile(
    r"\b(inn|tavern|town|village|city|keep|castle|dungeon|cave|forest|valley"
    r"|mountain|swamp|ruins|market|temple|shrine|hall|fortress|port|harbor"
    r"|crossroads|road|bridge|gate|district|quarter|plaza|outpost|camp)\b",
    re.IGNORECASE,
)


def _extract_candidate_names(text: str) -> list[str]:
    """
    Extract capitalized words/phrases that look like proper nouns.
    Returns single tokens; multi-word names are not reliably detectable without NLP,
    so we keep it simple and precise rather than aggressive.
    """
    # Find capitalized words that aren't at the very start of a sentence
    # (to reduce false positives from sentence-start capitals)
    candidates: list[str] = []
    # Strip sentences and look for mid-sentence capitals
    tokens = re.findall(r"[A-Z][a-z]{2,}", text)
    for tok in tokens:
        if tok not in _COMMON_WORDS and len(tok) >= 3:
            candidates.append(tok)
    return candidates


def _classify_entity(name: str, context: str) -> str:
    """
    Return 'items', 'places', or 'npcs' based on surrounding context.
    Looks for nearby keyword hints within ±60 chars of the name in context.
    """
    idx = context.find(name)
    if idx == -1:
        return "npcs"
    snippet = context[max(0, idx - 60): idx + 60 + len(name)].lower()
    if _ITEM_KEYWORDS.search(snippet):
        return "items"
    if _PLACE_KEYWORDS.search(snippet):
        return "places"
    return "npcs"


def update_lore_bible(
    lore: dict[str, dict[str, str]],
    narration: str,
    turn_num: int,
) -> None:
    """
    Parse narration for named entities and add new ones to the lore bible in-place.
    Skips names already known. Keeps descriptions brief.
    """
    candidates = _extract_candidate_names(narration)
    for name in candidates:
        category = _classify_entity(name, narration)
        if name not in lore[category]:
            # Build a short context note from the surrounding sentence
            # Find the sentence containing the name
            sentences = re.split(r"(?<=[.!?])\s+", narration)
            note_sentence = ""
            for sent in sentences:
                if name in sent:
                    note_sentence = sent.strip()
                    break
            # Truncate to 60 chars for compactness
            if note_sentence:
                note = f"turn {turn_num}: {note_sentence[:60]}"
            else:
                note = f"turn {turn_num}"
            lore[category][name] = note


def lore_bible_summary(lore: dict[str, dict[str, str]], max_tokens_approx: int = 380) -> str:
    """
    Render the lore bible as a compact block for injection into the player prompt.
    Stays under max_tokens_approx (rough: 1 token ≈ 4 chars, so ~1520 chars).
    Prioritizes most-recently-added entries by keeping the dict insertion order.
    """
    if not any(lore.values()):
        return ""

    max_chars = max_tokens_approx * 4
    lines: list[str] = ["What you know so far:"]

    sections = [
        ("NPCs", lore["npcs"]),
        ("Places", lore["places"]),
        ("Items", lore["items"]),
    ]
    for section_name, entries in sections:
        if not entries:
            continue
        lines.append(f"  {section_name}:")
        for name, note in entries.items():
            line = f"    - {name}: {note}"
            lines.append(line)

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars].rsplit("\n", 1)[0] + "\n    (... truncated)"
    return result

# ──────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mørkyn autonomous player-agent playtest")
    p.add_argument("--turns", type=int, default=DEFAULT_TURNS,
                   help=f"Number of turns to play (default {DEFAULT_TURNS})")
    p.add_argument("--ollama-url", type=str, default=DEFAULT_OLLAMA_URL,
                   help=f"Ollama base URL (default {DEFAULT_OLLAMA_URL})")
    p.add_argument("--port", type=int, default=0,
                   help="Port for the Morkyn server (default: auto-find a free port)")
    p.add_argument("--keep-db", action="store_true",
                   help="Keep the playtest DB after the run")
    p.add_argument("--report", type=str, default="player_agent_report.txt",
                   help="Output report filename (default: player_agent_report.txt)")
    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────────────────────────────────────

def find_free_port() -> int:
    """Bind to port 0, let the OS assign, then release."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_get(url: str, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def http_post(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ──────────────────────────────────────────────────────────────────────────────
# Ollama helpers
# ──────────────────────────────────────────────────────────────────────────────

def ollama_list_models(base_url: str) -> list[str]:
    try:
        data = http_get(f"{base_url}/api/tags", timeout=10)
        models = data.get("models") or []
        return [m["name"] for m in models if isinstance(m, dict) and m.get("name")]
    except Exception as e:
        return []


def pick_model(models: list[str]) -> str:
    """Prefer 7B/8B-ish sizes; fall back to whatever is available."""
    prefer_patterns = [
        r"8b", r"7b", r"mistral", r"llama3\.1:8b", r"llama3:8b",
        r"gemma.*7b", r"phi.*mini", r"phi3", r"orca.*mini",
        r"neural.*chat", r"qwen.*7b", r"deepseek.*7b",
    ]
    avoid_patterns = [r"34b", r"70b", r"72b", r"180b"]

    def score(name: str) -> int:
        n = name.lower()
        for pat in avoid_patterns:
            if re.search(pat, n):
                return -100
        for i, pat in enumerate(prefer_patterns):
            if re.search(pat, n):
                return 1000 - i
        return 500

    if not models:
        return "llama3.1"
    return sorted(models, key=score, reverse=True)[0]


def ollama_chat(
    base_url: str,
    model: str,
    system: str,
    user: str,
    timeout: int = PLAYER_BRAIN_TIMEOUT,
) -> str:
    """Send a chat completion to Ollama and return the assistant's reply text."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            "num_predict": 120,
            "temperature": 0.85,
            "top_p": 0.95,
        },
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    return str((data.get("message") or {}).get("content") or "").strip()


# ──────────────────────────────────────────────────────────────────────────────
# Narration extraction (mirrors playtest.py logic)
# ──────────────────────────────────────────────────────────────────────────────

def extract_narration(payload: dict[str, Any]) -> str:
    turn = payload.get("turn") or {}
    for key in ("narration", "text", "response"):
        val = turn.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    segs = turn.get("narration_segments")
    if isinstance(segs, list):
        parts = []
        for s in segs:
            if isinstance(s, dict):
                parts.append(str(s.get("text") or s.get("narration") or ""))
            elif isinstance(s, str):
                parts.append(s)
        joined = " ".join(p for p in parts if p)
        if joined.strip():
            return joined.strip()
    # Sometimes the narration is at the top level (e.g. opening scene)
    for key in ("narration", "text", "response", "opening"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def state_summary(state: dict[str, Any]) -> str:
    """
    Build a clean, player-visible character sheet from /api/state.

    ONLY includes information a real player would see on their character sheet:
    name, level, HP, mana/stamina, gold, equipped items, active conditions,
    location name, and active quests.  No internal IDs, DB fields, raw JSON,
    system data, or any behind-the-scenes engine state.
    """
    player = state.get("player") or {}
    lines: list[str] = []

    # ── Identity ──────────────────────────────────────────────────────────────
    name = str(player.get("name") or "Unknown")
    level = player.get("level") or 1
    xp = player.get("xp")
    xp_next = player.get("xp_next")
    if xp is not None and xp_next is not None:
        lines.append(f"Name: {name}  |  Level {level}  |  XP: {xp}/{xp_next}")
    else:
        lines.append(f"Name: {name}  |  Level {level}")

    # ── Vitals ────────────────────────────────────────────────────────────────
    vitals: list[str] = []
    hp = player.get("hp")
    hp_max = player.get("hp_max")
    if hp is not None:
        vitals.append(f"HP {hp}/{hp_max or '?'}")
    mana = player.get("mana")
    mana_max = player.get("mana_max")
    if mana is not None:
        vitals.append(f"Mana {mana}/{mana_max or '?'}")
    stamina = player.get("stamina")
    stamina_max = player.get("stamina_max")
    if stamina is not None:
        vitals.append(f"Stamina {stamina}/{stamina_max or '?'}")
    if vitals:
        lines.append("Vitals: " + "  |  ".join(vitals))

    # ── Gold ──────────────────────────────────────────────────────────────────
    gold = player.get("gold") if player.get("gold") is not None else player.get("coins")
    if gold is not None:
        lines.append(f"Gold: {gold}")

    # ── Location ─────────────────────────────────────────────────────────────
    locations = state.get("locations") or []
    if locations and isinstance(locations[0], dict):
        loc_name = str(locations[0].get("name") or "").strip()
        if loc_name:
            lines.append(f"Location: {loc_name}")

    # ── Equipped items (what the player is wearing/wielding) ─────────────────
    inventory = state.get("inventory") or []
    equipped: list[str] = []
    for item in inventory:
        if not isinstance(item, dict):
            continue
        slot = item.get("equipped_slot") or item.get("slot")
        name_i = str(item.get("name") or "").strip()
        if slot and name_i:
            equipped.append(f"{name_i} ({slot})")
    if equipped:
        lines.append("Equipped: " + ", ".join(equipped[:8]))

    # ── Active conditions / status effects ────────────────────────────────────
    conditions = state.get("conditions") or []
    cond_names: list[str] = []
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        label = str(cond.get("name") or cond.get("summary") or "").strip()
        if label:
            cond_names.append(label)
    if cond_names:
        lines.append("Conditions: " + ", ".join(cond_names[:6]))

    # ── Active quests (names only — no internal IDs) ──────────────────────────
    quests = state.get("quests") or state.get("active_quests") or []
    quest_names: list[str] = []
    for q in quests:
        if not isinstance(q, dict):
            continue
        q_name = str(q.get("name") or q.get("title") or q.get("summary") or "").strip()
        if q_name:
            quest_names.append(q_name)
    if quest_names:
        lines.append("Active quests: " + "; ".join(quest_names[:4]))

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Bug / quality checks
# ──────────────────────────────────────────────────────────────────────────────

BAD_PHRASES = [
    ("As an AI", "model broke character"),
    ("I am an AI", "model broke character"),
    ("I'm an AI", "model broke character"),
    ("language model", "model broke character"),
    ("I cannot assist", "refusal"),
    ("I'm sorry, I can't", "refusal"),
    ("[ERROR]", "error string in output"),
]


def check_narration_quality(
    turn_num: int,
    narration: str,
    prev_narrations: list[str],
) -> list[str]:
    issues: list[str] = []
    if not narration:
        issues.append("EMPTY_RESPONSE: no narration text returned")
        return issues
    if len(narration) < 40:
        issues.append(f"SHORT_RESPONSE ({len(narration)} chars)")
    for phrase, label in BAD_PHRASES:
        if phrase.lower() in narration.lower():
            issues.append(f"CONTENT_ISSUE ({label}): found '{phrase}'")
    # Repetition check
    recent = prev_narrations[-REPETITION_WINDOW:]
    for i, prev in enumerate(recent):
        if not prev:
            continue
        w_new = set(narration.lower().split())
        w_old = set(prev.lower().split())
        if len(w_new) > 10 and len(w_old) > 10:
            overlap = len(w_new & w_old) / max(len(w_new), len(w_old))
            if overlap > REPETITION_THRESHOLD:
                back = len(recent) - i
                issues.append(f"HIGH_REPETITION ({overlap:.0%} overlap with turn {turn_num - back})")
                break
    return issues


def check_action_quality(action: str, prev_action: str) -> list[str]:
    issues: list[str] = []
    if not action.strip():
        issues.append("PLAYER_BRAIN_EMPTY: no action returned")
        return issues
    if prev_action and action.strip().lower() == prev_action.strip().lower():
        issues.append("PLAYER_BRAIN_REPEAT: identical action as previous turn")
    for phrase, label in BAD_PHRASES:
        if phrase.lower() in action.lower():
            issues.append(f"PLAYER_BRAIN_ISSUE ({label}): found '{phrase}'")
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# Morkyn server lifecycle
# ──────────────────────────────────────────────────────────────────────────────

def start_morkyn_server(port: int, db_path: str) -> subprocess.Popen:
    """Launch uvicorn as a subprocess with a fresh DB."""
    env = dict(os.environ)
    env["AI_RPG_DB"] = db_path
    env["AI_RPG_MAX_RESPONSE_TOKENS"] = env.get("AI_RPG_MAX_RESPONSE_TOKENS", "600")
    env["AI_RPG_RESPONSE_HARD_CAP_TOKENS"] = env.get("AI_RPG_RESPONSE_HARD_CAP_TOKENS", "800")

    # Use the project's venv if it exists
    venv = SCRIPT_DIR / ".venv"
    if sys.platform == "win32":
        python = str(venv / "Scripts" / "python.exe") if venv.exists() else sys.executable
    else:
        python = str(venv / "bin" / "python") if venv.exists() else sys.executable

    cmd = [
        python, "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning",
    ]
    print(f"[SERVER] Starting: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(SCRIPT_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def wait_for_server(base_url: str, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
    """Poll /api/version until the server responds or timeout."""
    deadline = time.time() + timeout
    url = f"{base_url}/api/version"
    while time.time() < deadline:
        try:
            http_get(url, timeout=5)
            return True
        except Exception:
            time.sleep(1.5)
    return False


def kill_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    print("[SERVER] Terminating…")
    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Report writer
# ──────────────────────────────────────────────────────────────────────────────

def write_report(
    path: str,
    model: str,
    turn_log: list[dict[str, Any]],
    bugs: list[dict[str, Any]],
    quality_issues: list[dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    completed: int,
    total: int,
) -> None:
    lines: list[str] = []

    elapsed = (end_time - start_time).total_seconds()
    pass_fail = "PASS" if not bugs else f"FAIL ({len(bugs)} bugs found)"

    lines += [
        "=" * 72,
        "MØRKYN  —  PLAYER AGENT PLAYTEST REPORT",
        "=" * 72,
        f"Model:          {model}",
        f"Started:        {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Finished:       {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Elapsed:        {elapsed:.0f}s  ({elapsed/60:.1f} min)",
        f"Turns played:   {completed} / {total}",
        f"Bugs found:     {len(bugs)}",
        f"Quality issues: {len(quality_issues)}",
        f"Verdict:        {pass_fail}",
        "",
    ]

    # ── Bug list ──────────────────────────────────────────────────────────────
    if bugs:
        lines += ["─" * 72, "BUGS", "─" * 72]
        for b in bugs:
            lines.append(f"\nTurn {b['turn']}:")
            lines.append(f"  Action:  {b.get('action', '(none)')}")
            lines.append(f"  Error:   {b.get('error', '')}")
            if b.get("traceback"):
                lines.append("  Traceback (truncated):")
                for tb_line in b["traceback"].splitlines()[-6:]:
                    lines.append(f"    {tb_line}")
        lines.append("")

    # ── Quality issues ────────────────────────────────────────────────────────
    if quality_issues:
        lines += ["─" * 72, "LLM QUALITY FLAGS", "─" * 72]
        for q in quality_issues:
            lines.append(f"\nTurn {q['turn']}:")
            lines.append(f"  Action:    {q.get('action', '')[:80]}")
            for issue in q.get("issues", []):
                lines.append(f"  ⚠  {issue}")
            snippet = q.get("narration_snippet") or q.get("action_snippet") or ""
            if snippet:
                lines.append(f"  Snippet:   {snippet[:120]}")
        lines.append("")

    # ── Full turn log ─────────────────────────────────────────────────────────
    lines += ["─" * 72, "FULL TURN LOG", "─" * 72, ""]
    for entry in turn_log:
        t = entry["turn"]
        action = entry.get("action", "(opening)")
        narration_len = entry.get("narration_len", 0)
        elapsed_t = entry.get("elapsed", 0.0)
        flag = "  ⚠" if entry.get("issues") else ""
        lines.append(
            f"Turn {t:3d}  [{elapsed_t:5.1f}s]  {narration_len:5d} chars{flag}"
        )
        lines.append(f"  Action:    {action[:120]}")
        narration_snippet = entry.get("narration_snippet", "")
        if narration_snippet:
            lines.append(f"  Narration: {narration_snippet[:120]}")
        for issue in entry.get("issues", []):
            lines.append(f"  ⚠  {issue}")
        lines.append("")

    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print(f"[REPORT] Written → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    start_time = datetime.now()

    # ── 0. Sanity: is Ollama reachable? ──────────────────────────────────────
    available_models = ollama_list_models(args.ollama_url)
    if not available_models:
        print(
            f"[FATAL] Cannot reach Ollama at {args.ollama_url} or no models are installed.\n"
            "        Make sure Ollama is running:  ollama serve\n"
            "        And at least one model is pulled, e.g.:  ollama pull phi3:mini"
        )
        return 1

    model = pick_model(available_models)
    print(f"[MODEL] Available: {available_models}")
    print(f"[MODEL] Selected:  {model}  (used for both game engine and player brain)")

    # ── 1. Set up DB path ────────────────────────────────────────────────────
    data_dir = SCRIPT_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = str(data_dir / "player_agent_world.db")
    if not args.keep_db:
        db = Path(db_path)
        if db.exists():
            db.unlink()
            print(f"[DB] Removed stale DB: {db}")

    # ── 2. Start Morkyn server ───────────────────────────────────────────────
    port = args.port or find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[SERVER] Binding on port {port}  (base_url={base_url})")

    proc = start_morkyn_server(port, db_path)
    print(f"[SERVER] PID {proc.pid}. Waiting for startup (up to {SERVER_STARTUP_TIMEOUT}s)…")

    if not wait_for_server(base_url, timeout=SERVER_STARTUP_TIMEOUT):
        stderr_output = ""
        try:
            stderr_output = proc.stderr.read().decode(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass
        kill_server(proc)
        print(f"[FATAL] Server did not start within {SERVER_STARTUP_TIMEOUT}s.")
        if stderr_output:
            print("[STDERR]\n" + stderr_output[:2000])
        return 1

    print(f"[SERVER] Ready at {base_url}")

    # ── 3. Configure the game's LLM to use our chosen Ollama model ───────────
    try:
        http_post(f"{base_url}/api/model-config", {
            "provider": "ollama",
            "ollama_base_url": args.ollama_url,
            "ollama_model": model,
            "response_token_cap": 600,
            "response_token_hard_cap": 800,
        }, timeout=15)
        print(f"[GAME]   Model config set: ollama/{model}")
    except Exception as e:
        print(f"[WARN]   Could not set model config (non-fatal): {e}")

    # ── 4. Start a fresh playthrough ─────────────────────────────────────────
    setup_payload: dict[str, Any] = {
        "player_name": "Aldric",
        "player_age": "27",
        "player_sex": "male",
        "backstory_mode": "known",
        "character_backstory": (
            "A wandering sellsword from the eastern marches, "
            "seeking coin and perhaps something worth dying for."
        ),
        "world_style": "frontier dark fantasy",
        "difficulty": "normal",
        "narration_detail": "rich",
        "tone": "grounded adventure",
        "economy": "scarce",
        "loot_rarity": "earned and uncommon",
        "magic_level": "rare",
        "tech_level": "iron age",
        "start_location": "frontier town",
        "npc_density": "moderate",
        "quest_style": "emergent",
        "death_rules": "downed, not deleted",
        "skill_style": "standard",
        "leveling_system": True,
        "dice_checks_enabled": True,
        "dice_sides": 20,
    }

    print("[GAME]   Starting playthrough (this may take a moment)…")
    t0 = time.time()
    try:
        setup_result = http_post(f"{base_url}/api/setup", setup_payload, timeout=TURN_HTTP_TIMEOUT)
        opening_elapsed = time.time() - t0
        opening_narration = extract_narration(setup_result)
        print(f"[GAME]   Opening scene done in {opening_elapsed:.1f}s.")
        if opening_narration:
            print(f"[OPENING] {opening_narration[:200]}…")
        else:
            print("[WARN]   No narration in opening scene response.")
    except Exception as e:
        kill_server(proc)
        print(f"[FATAL] /api/setup failed: {e}")
        traceback.print_exc()
        return 1

    # ── 5. Main playtest loop ─────────────────────────────────────────────────
    turn_log: list[dict[str, Any]] = []
    bugs: list[dict[str, Any]] = []
    quality_issues: list[dict[str, Any]] = []
    narrations: list[str] = [opening_narration]
    prev_action = ""
    last_narration = opening_narration

    # Lore bible: tracks named entities discovered across turns
    lore_bible: dict[str, dict[str, str]] = {"npcs": {}, "places": {}, "items": {}}
    # Seed lore bible from the opening narration (turn 0)
    if opening_narration:
        update_lore_bible(lore_bible, opening_narration, 0)

    # Log the opening
    turn_log.append({
        "turn": 0,
        "action": "(opening scene)",
        "narration_len": len(opening_narration),
        "narration_snippet": opening_narration[:120],
        "elapsed": round(opening_elapsed, 2),
        "issues": [],
    })

    total_turns = args.turns
    completed = 0

    print(f"\n[LOOP]   Starting {total_turns}-turn autonomous loop…\n")

    for turn_num in range(1, total_turns + 1):
        turn_issues: list[str] = []
        action = ""
        narration = ""
        turn_elapsed = 0.0

        # ── a. Get current game state ─────────────────────────────────────
        stats_str = ""
        try:
            state = http_get(f"{base_url}/api/state", timeout=15)
            stats_str = state_summary(state)
        except Exception as e:
            stats_str = "(state unavailable)"
            turn_issues.append(f"STATE_FETCH_ERROR: {e}")

        # ── b. Ask the player brain for the next action ───────────────────
        # IMPORTANT: the player brain receives ONLY what a real player would see —
        # the narrative text, a clean character sheet, and the lore bible summary.
        # No raw JSON, no internal engine state, no DB fields, no system data.
        lore_block = lore_bible_summary(lore_bible)
        lore_section = f"\n\n=== What you know so far ===\n{lore_block}" if lore_block else ""
        user_prompt = (
            f"=== What just happened (narrative) ===\n{last_narration}\n\n"
            f"=== Your character sheet ===\n{stats_str}"
            f"{lore_section}\n\n"
            "What do you do next? Respond with your character's action in 1–2 sentences, "
            "first person, no preamble."
        )

        try:
            action = ollama_chat(
                base_url=args.ollama_url,
                model=model,
                system=PLAYER_BRAIN_SYSTEM,
                user=user_prompt,
            )
        except Exception as e:
            action = "I look around carefully to get my bearings."
            turn_issues.append(f"PLAYER_BRAIN_ERROR: {e} — using fallback action")

        # Strip any meta-phrases the model might prefix
        action = re.sub(r"^(action:|player action:|my action:)\s*", "", action, flags=re.IGNORECASE).strip()
        # Trim to 2 sentences max
        sentences = re.split(r"(?<=[.!?])\s+", action)
        if len(sentences) > 2:
            action = " ".join(sentences[:2])

        action_issues = check_action_quality(action, prev_action)
        turn_issues.extend(action_issues)

        print(f"  Turn {turn_num:3d}/{total_turns}  ▶  {action[:80]!r}")

        # ── c. Send action to Morkyn ─────────────────────────────────────
        t0 = time.time()
        try:
            turn_result = http_post(
                f"{base_url}/api/turn",
                {"text": action},
                timeout=TURN_HTTP_TIMEOUT,
            )
            turn_elapsed = time.time() - t0
            narration = extract_narration(turn_result)
            used_fallback = bool(turn_result.get("used_fallback"))
            if used_fallback:
                reason = str(turn_result.get("fallback_reason") or "unknown")
                turn_issues.append(f"FALLBACK: {reason}")
        except urllib.error.HTTPError as e:
            turn_elapsed = time.time() - t0
            err_body = ""
            try:
                err_body = e.read().decode(errors="replace")[:300]
            except Exception:
                pass
            turn_issues.append(f"HTTP_ERROR {e.code}: {err_body}")
            bugs.append({
                "turn": turn_num,
                "action": action,
                "error": f"HTTP {e.code}: {err_body}",
                "traceback": "",
            })
            print(f"         ⚠  HTTP {e.code}")
        except json.JSONDecodeError as e:
            turn_elapsed = time.time() - t0
            turn_issues.append(f"JSON_DECODE_ERROR: {e}")
            bugs.append({
                "turn": turn_num,
                "action": action,
                "error": f"JSON decode: {e}",
                "traceback": traceback.format_exc(),
            })
            print(f"         ⚠  JSON decode error")
        except Exception as e:
            turn_elapsed = time.time() - t0
            turn_issues.append(f"TURN_ERROR: {e}")
            bugs.append({
                "turn": turn_num,
                "action": action,
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            print(f"         ⚠  {e}")

        # ── d/e. Quality checks ───────────────────────────────────────────
        narr_issues = check_narration_quality(turn_num, narration, narrations)
        turn_issues.extend(narr_issues)

        if narration:
            narrations.append(narration)
            last_narration = narration
            # Update lore bible with entities from this turn's narration
            update_lore_bible(lore_bible, narration, turn_num)

        # ── f. Log ───────────────────────────────────────────────────────
        if turn_issues:
            for issue in turn_issues:
                print(f"         ⚠  {issue}")
            quality_issues.append({
                "turn": turn_num,
                "action": action,
                "issues": turn_issues,
                "narration_snippet": narration[:120],
            })

        turn_log.append({
            "turn": turn_num,
            "action": action,
            "narration_len": len(narration),
            "narration_snippet": narration[:120],
            "elapsed": round(turn_elapsed, 2),
            "issues": turn_issues,
        })

        flag = "  ⚠" if turn_issues else ""
        print(f"         ← {len(narration):5d} chars  {turn_elapsed:.1f}s{flag}")

        prev_action = action
        completed += 1

    # ── 6. Kill server ────────────────────────────────────────────────────────
    kill_server(proc)

    # ── 7. Write report ───────────────────────────────────────────────────────
    end_time = datetime.now()
    report_path = str(SCRIPT_DIR / args.report)
    write_report(
        path=report_path,
        model=model,
        turn_log=turn_log,
        bugs=bugs,
        quality_issues=quality_issues,
        start_time=start_time,
        end_time=end_time,
        completed=completed,
        total=total_turns,
    )

    verdict = "PASS" if not bugs else f"FAIL — {len(bugs)} bugs"
    print(f"\n[DONE]  {completed}/{total_turns} turns  |  bugs: {len(bugs)}  |  quality flags: {len(quality_issues)}  |  {verdict}")
    return 0 if not bugs else 1


if __name__ == "__main__":
    sys.exit(main())
