"""
playtest.py — Automated playtest harness for Mørkyn
====================================================
Run from the project root:
    python playtest.py [--turns 120] [--model qwen3:8b] [--keep-db]

The script spins up a fresh game world on MLE (Morkyn LLM Engine),
drives 100+ turns of varied player behaviour, and writes playtest_report.txt
when it's done.  Errors are caught turn-by-turn so a single crash never
stops the whole run. Until the welding rig is connected, MLE turns say so.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# 0.  Bootstrap: make sure we're running from the project root
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Argument parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mørkyn automated playtest harness")
    p.add_argument("--turns", type=int, default=120, help="Number of turns to play (default 120)")
    p.add_argument("--model", type=str, default="",
                   help="MLE model name (default qwen3:8b, or MLE_MODEL)")
    p.add_argument("--keep-db", action="store_true",
                   help="Keep the playtest DB after the run (default: use temp path)")
    p.add_argument("--db-path", type=str, default="",
                   help="Custom DB path (default: data/playtest_world.db)")
    p.add_argument("--report", type=str, default="playtest_report.txt",
                   help="Output report filename (default: playtest_report.txt)")
    return p.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# 2.  MLE model name
# ──────────────────────────────────────────────────────────────────────────────

def chosen_model(forced: str = "") -> str:
    """Name stored for MLE. Nothing is downloaded or listed from a server."""
    name = (forced or os.getenv("MLE_MODEL") or os.getenv("PLAYTEST_MLE_MODEL") or "qwen3:8b").strip()
    return name or "qwen3:8b"


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Environment configuration (must happen BEFORE importing app modules)
# ──────────────────────────────────────────────────────────────────────────────

def configure_environment(model: str, db_path: str) -> None:
    os.environ["AI_RPG_MODEL_PROVIDER"] = "mle"
    os.environ["MLE_MODEL"] = model
    os.environ["AI_RPG_DB"] = db_path
    for gone in ("OLLAMA_MODEL", "OLLAMA_BASE_URL", "OLLAMA_THINK", "OLLAMA_CONTEXT_TOKENS"):
        os.environ.pop(gone, None)
    # Reduce token caps slightly so turns are faster in automated runs
    os.environ.setdefault("AI_RPG_MAX_RESPONSE_TOKENS", "600")
    os.environ.setdefault("AI_RPG_RESPONSE_HARD_CAP_TOKENS", "800")
    print(f"[ENV] provider=mle  model={model}  db={db_path}")


# ──────────────────────────────────────────────────────────────────────────────
# 4.  Player-input sequences (100+ varied, natural-language actions)
# ──────────────────────────────────────────────────────────────────────────────

# Grouped by intent so the harness can weight/shuffle sensibly
EXPLORE_INPUTS = [
    "I look around, taking in my surroundings.",
    "I examine the area carefully.",
    "I walk toward the forest on the edge of the clearing.",
    "I head north, following the dirt road.",
    "I peer through the fog, trying to make out what lies ahead.",
    "I explore the nearby ruins, stepping carefully over loose stones.",
    "I climb the hill to get a better view of the valley.",
    "I follow the sound of running water.",
    "I search the abandoned wagon for anything useful.",
    "I crouch behind the bushes and observe the camp below.",
    "I investigate the old well near the inn.",
    "I wander through the market stalls, seeing what's on offer.",
    "I check the notice board outside the tavern.",
    "I enter the blacksmith's shop.",
    "I slip down the alley between the buildings.",
    "I go into the inn and find a seat by the fire.",
    "I head toward the city gates.",
    "I explore the cave entrance carefully, torch in hand.",
    "I scan the tree line for movement.",
    "I approach the campfire I spotted earlier.",
]

FIGHT_INPUTS = [
    "I attack the bandit with my sword!",
    "I draw my weapon and charge the nearest enemy.",
    "I dodge to the side and strike at the bandit's flank.",
    "I try to disarm the guard with a quick twist of my wrist.",
    "I throw a rock at the wolf to distract it, then move in close.",
    "I aim for the enemy's weak spot and strike hard.",
    "I parry the incoming blow and counter-attack.",
    "I use my shield to bash the attacker and create some distance.",
    "I feint left, then slash right at the bandit leader.",
    "I roar a battle cry and press the attack aggressively.",
    "I try to knock the bandit unconscious rather than kill them.",
    "I go for the killing blow while the enemy is staggered.",
    "I grab the bandit's weapon arm and try to overpower them.",
    "Flee! I run as fast as I can away from the fight.",
    "I back away, putting a table between me and the attacker.",
]

LOOT_INPUTS = [
    "I pick up the sword lying on the ground.",
    "I search the bandit's body for valuables.",
    "I grab the coin purse from the fallen guard.",
    "I examine the strange amulet half-buried in the dirt.",
    "I take the health potion from the shelf.",
    "I stuff the loose coins into my pack.",
    "I pick up the bow and inspect its condition.",
    "I equip the iron sword I just found.",
    "I put on the leather armour from the chest.",
    "I equip the shield on my arm.",
    "I try on the ring I found and see if I feel anything.",
    "I open the chest in the corner and see what's inside.",
    "I loot the room quickly before anyone arrives.",
    "I take the map from the dead courier's satchel.",
    "I pocket the key I found hanging on the wall.",
]

TRADE_INPUTS = [
    "I trade with the merchant at the stall.",
    "I ask the shopkeeper what they have for sale.",
    "I offer to sell my spare dagger to the trader.",
    "I negotiate a better price for the healing herbs.",
    "I buy the cheapest health potion available.",
    "I haggle over the price of the iron shield.",
    "I ask the blacksmith to repair my weapon.",
    "I spend some coin on a hot meal and a room for the night.",
    "I check how much the sword would fetch if I sold it.",
    "I try to trade some of my food rations for a torch.",
]

SOCIAL_INPUTS = [
    "I strike up a conversation with the innkeeper.",
    "I ask the old man by the fire if he knows anything about this area.",
    "I tell the guard I'm just passing through.",
    "I compliment the barmaid on the ale and ask her name.",
    "I ask the merchant about any trouble on the roads lately.",
    "I try to persuade the farmer to let me stay in his barn tonight.",
    "I ask the village elder about the disappearances.",
    "I introduce myself to the group of travellers at the table.",
    "I listen carefully to what the drunken soldier is muttering.",
    "I try to befriend the nervous-looking young man in the corner.",
    "I ask about local rumours — anything interesting going on?",
    "I tell the priest I'm looking for work.",
    "I confront the suspicious hooded figure near the docks.",
    "I ask the child where their parents are.",
    "I attempt to intimidate the gang's lookout into letting me pass.",
]

QUEST_INPUTS = [
    "I ask about any quests or odd jobs available.",
    "I agree to help the merchant recover their stolen goods.",
    "I ask the innkeeper who posted the job on the notice board.",
    "I ask what reward is offered for dealing with the bandits.",
    "I investigate the clue the widow mentioned — the broken lantern.",
    "I travel to the location the old man described.",
    "I report back to the quest-giver with what I found.",
    "I follow up on the rumour about the missing shepherd.",
    "I tell the guard captain about the bandit camp I discovered.",
    "I accept the urgent courier job — I need the money.",
]

ABILITY_INPUTS = [
    "I drink the health potion to restore my strength.",
    "I use my stealth ability to slip past the guard unnoticed.",
    "I concentrate and try to channel whatever power I feel inside me.",
    "I attempt to pick the lock on the door.",
    "I use my survival skills to find food and water nearby.",
    "I try to track the creature's trail through the mud.",
    "I attempt to patch my wounds before the blood loss gets worse.",
    "I use my knowledge of herbs to treat the injured traveller.",
    "I focus and attempt to read the old runes on the wall.",
    "I call upon any luck I have left and take the risk.",
]

MISC_INPUTS = [
    "I rest for a while, keeping watch.",
    "I make camp for the night.",
    "I light a torch — it's getting dark.",
    "I write a short entry in my journal about what happened today.",
    "I pray at the roadside shrine.",
    "I study the map I found and try to figure out where I am.",
    "I wait and see if anything changes.",
    "I hide and observe without acting.",
    "I try to remember anything I know about this kind of situation.",
    "I check my inventory and assess what I'm carrying.",
    "I take a moment to breathe and think through my options.",
    "What's the name of this place again? I look for any signpost.",
    "I check if there's a back door or another way out.",
    "I ask myself: is this really worth the risk?",
    "I push on — I can't afford to slow down now.",
]

ALL_INPUTS_BY_CATEGORY: dict[str, list[str]] = {
    "explore": EXPLORE_INPUTS,
    "fight": FIGHT_INPUTS,
    "loot": LOOT_INPUTS,
    "trade": TRADE_INPUTS,
    "social": SOCIAL_INPUTS,
    "quest": QUEST_INPUTS,
    "ability": ABILITY_INPUTS,
    "misc": MISC_INPUTS,
}

# Build a weighted sequence that simulates realistic play
def build_turn_sequence(n: int) -> list[tuple[str, str]]:
    """Return (category, input_text) pairs for n turns."""
    import random

    # Weights reflect how often each category naturally appears
    weights = {
        "explore": 25,
        "fight": 15,
        "loot": 12,
        "trade": 8,
        "social": 15,
        "quest": 10,
        "ability": 8,
        "misc": 7,
    }

    rng = random.Random(42)  # deterministic for reproducibility
    sequence: list[tuple[str, str]] = []

    # Always start with exploration
    opening_explores = ["I look around carefully to get my bearings.",
                        "I take stock of where I am and what I can see."]
    for text in opening_explores:
        sequence.append(("explore", text))

    # Fill remaining turns with weighted-random categories
    categories = list(weights.keys())
    weight_list = [weights[c] for c in categories]

    used: dict[str, set[int]] = {c: set() for c in categories}

    while len(sequence) < n:
        cat = rng.choices(categories, weights=weight_list, k=1)[0]
        pool = ALL_INPUTS_BY_CATEGORY[cat]
        # Pick an unused index; cycle if exhausted
        available = [i for i in range(len(pool)) if i not in used[cat]]
        if not available:
            used[cat].clear()
            available = list(range(len(pool)))
        idx = rng.choice(available)
        used[cat].add(idx)
        sequence.append((cat, pool[idx]))

    return sequence[:n]


# ──────────────────────────────────────────────────────────────────────────────
# 5.  LLM quality analysis helpers
# ──────────────────────────────────────────────────────────────────────────────

def extract_narration(payload: dict[str, Any]) -> str:
    """Pull the narration text out of the turn payload."""
    turn = payload.get("turn") or {}
    # Try various known keys
    for key in ("narration", "text", "response"):
        val = turn.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # narration_segments list
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
    return ""


def check_narration_quality(
    turn_num: int,
    player_input: str,
    narration: str,
    prev_narrations: list[str],
) -> list[str]:
    """Return a list of quality issue strings (empty = clean)."""
    issues: list[str] = []

    if not narration:
        issues.append("EMPTY_RESPONSE: no narration text returned")
        return issues

    if len(narration) < 40:
        issues.append(f"SHORT_RESPONSE ({len(narration)} chars): may be truncated or error")

    # Repetition: check if narration is near-duplicate of a recent one
    if prev_narrations:
        recent = prev_narrations[-5:]
        for i, prev in enumerate(recent):
            if not prev:
                continue
            # Simple word-overlap ratio
            words_new = set(narration.lower().split())
            words_old = set(prev.lower().split())
            if len(words_new) > 10 and len(words_old) > 10:
                overlap = len(words_new & words_old) / max(len(words_new), len(words_old))
                if overlap > 0.75:
                    issues.append(
                        f"HIGH_REPETITION ({overlap:.0%} word overlap with turn {turn_num - len(recent) + i})"
                    )
                    break

    # Wrong-name check: if input names a specific person, that name should appear
    # in the narration (or at least be acknowledged)
    input_lower = player_input.lower()
    name_hints = re.findall(r"\b([A-Z][a-z]{2,})\b", player_input)
    for name in name_hints:
        if name in {"I", "The", "My", "He", "She", "It", "We", "They"}:
            continue
        if name.lower() not in narration.lower() and len(narration) > 100:
            # Only flag if the name looks like a proper noun and narration is substantial
            if re.search(r"\b" + re.escape(name) + r"\b", player_input):
                pass  # Not definitive enough to flag — skip

    # Context failure markers
    bad_phrases = [
        ("I cannot", "possible refusal marker"),
        ("I'm sorry", "possible refusal marker"),
        ("As an AI", "model broke character"),
        ("I am an AI", "model broke character"),
        ("language model", "model broke character"),
        ("[ERROR]", "error string in output"),
        ("{", "possible JSON leak in narration"),
    ]
    for phrase, label in bad_phrases:
        if phrase.lower() in narration.lower():
            issues.append(f"CONTENT_ISSUE ({label}): found '{phrase}'")

    return issues


# ──────────────────────────────────────────────────────────────────────────────
# 6.  Main playtest runner
# ──────────────────────────────────────────────────────────────────────────────

class PlaytestRun:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.start_time = datetime.now()

        self.model = chosen_model(args.model)

        # DB path
        if args.db_path:
            self.db_path = args.db_path
        else:
            Path("data").mkdir(exist_ok=True)
            self.db_path = "data/playtest_world.db"

        # Remove any stale playtest DB from a previous run (fresh slate)
        if not args.keep_db:
            db = Path(self.db_path)
            if db.exists():
                db.unlink()
                print(f"[INFO] Removed stale playtest DB: {db}")

        configure_environment(self.model, self.db_path)

        # Tracking
        self.turn_log: list[dict[str, Any]] = []  # one entry per turn
        self.errors: list[dict[str, Any]] = []    # only turns with issues
        self.quality_issues: list[dict[str, Any]] = []
        self.narrations: list[str] = []

    # ------------------------------------------------------------------

    def _import_app(self) -> None:
        """Import app modules AFTER env is configured."""
        print("[INFO] Importing Mørkyn app modules …")
        global init_db, play_turn, start_playthrough_with_opening, get_state, update_model_config
        from app.db import init_db  # type: ignore
        from app.world import play_turn, start_playthrough_with_opening, get_state  # type: ignore
        from app.llm import update_model_config  # type: ignore
        print("[INFO] App modules imported OK.")

    # ------------------------------------------------------------------

    def _init_game(self) -> bool:
        """Initialise DB, configure LLM in DB, and start a fresh playthrough."""
        try:
            init_db()
            print("[INFO] DB initialised.")
        except Exception as e:
            print(f"[FATAL] init_db failed: {e}")
            traceback.print_exc()
            return False

        # Push model config into the DB so world.py picks it up reliably
        try:
            update_model_config({
                "provider": "mle",
                "mle_model": self.model,
            })
            print(f"[INFO] Model config saved: mle / {self.model}")
        except Exception as e:
            print(f"[WARN] update_model_config failed (non-fatal): {e}")

        # Start a minimal playthrough
        options: dict[str, Any] = {
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

        print("[INFO] Starting playthrough with opening scene …")
        t0 = time.time()
        try:
            result = start_playthrough_with_opening(options)
            elapsed = time.time() - t0
            print(f"[INFO] Opening scene done in {elapsed:.1f}s.")
            narration = extract_narration(result)
            if narration:
                print(f"[OPENING] {narration[:200]} …")
            else:
                print("[WARN] Opening scene returned no narration.")
            self.turn_log.append({
                "turn": 0,
                "category": "opening",
                "input": "(opening scene)",
                "narration_len": len(narration),
                "elapsed": round(elapsed, 2),
                "used_fallback": result.get("used_fallback", False),
                "errors": [],
            })
            self.narrations.append(narration)
        except Exception as e:
            print(f"[ERROR] start_playthrough_with_opening failed: {e}")
            traceback.print_exc()
            self.errors.append({
                "turn": 0,
                "input": "(opening scene)",
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            return False

        return True

    # ------------------------------------------------------------------

    def run(self) -> None:
        self._import_app()
        if not self._init_game():
            print("[FATAL] Could not start the game. Aborting.")
            self._write_report(completed=0)
            return

        sequence = build_turn_sequence(self.args.turns)
        total = len(sequence)
        print(f"\n[INFO] Starting {total}-turn playtest …\n")

        completed = 0
        for turn_num, (category, player_input) in enumerate(sequence, start=1):
            print(f"  Turn {turn_num:3d}/{total}  [{category:7s}]  {player_input[:60]!r}")
            t0 = time.time()
            turn_errors: list[str] = []
            narration = ""

            try:
                payload = play_turn(player_input, input_kind="player")
                elapsed = time.time() - t0

                used_fallback = bool(payload.get("used_fallback"))
                fallback_reason = str(payload.get("fallback_reason") or "")
                narration = extract_narration(payload)

                if used_fallback:
                    turn_errors.append(f"FALLBACK: {fallback_reason or 'unknown reason'}")

                # Check LLM quality
                quality_issues = check_narration_quality(
                    turn_num, player_input, narration, self.narrations
                )
                turn_errors.extend(quality_issues)

                if turn_errors:
                    for issue in turn_errors:
                        print(f"    ⚠  {issue}")
                    self.quality_issues.append({
                        "turn": turn_num,
                        "category": category,
                        "input": player_input,
                        "issues": turn_errors,
                        "narration_snippet": narration[:120],
                    })

                self.narrations.append(narration)
                self.turn_log.append({
                    "turn": turn_num,
                    "category": category,
                    "input": player_input,
                    "narration_len": len(narration),
                    "elapsed": round(elapsed, 2),
                    "used_fallback": used_fallback,
                    "errors": turn_errors,
                })
                completed += 1
                print(f"         → {len(narration)} chars, {elapsed:.1f}s"
                      + (" [FALLBACK]" if used_fallback else ""))

            except KeyboardInterrupt:
                print("\n[INTERRUPTED] Writing partial report …")
                break

            except Exception as e:
                elapsed = time.time() - t0
                tb = traceback.format_exc()
                error_entry = {
                    "turn": turn_num,
                    "category": category,
                    "input": player_input,
                    "error": str(e),
                    "traceback": tb,
                }
                self.errors.append(error_entry)
                self.turn_log.append({
                    "turn": turn_num,
                    "category": category,
                    "input": player_input,
                    "narration_len": 0,
                    "elapsed": round(elapsed, 2),
                    "used_fallback": False,
                    "errors": [f"EXCEPTION: {e}"],
                })
                print(f"    ✗  EXCEPTION: {e}")
                # Continue to the next turn — never crash the whole run
                time.sleep(0.5)
                continue

        print(f"\n[INFO] Playtest finished. {completed}/{total} turns completed.")
        self._write_report(completed=completed)

    # ------------------------------------------------------------------

    def _write_report(self, completed: int) -> None:
        report_path = Path(self.args.report)
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        # Aggregate stats
        elapsed_times = [e["elapsed"] for e in self.turn_log if e.get("elapsed")]
        avg_elapsed = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0
        max_elapsed = max(elapsed_times) if elapsed_times else 0
        min_elapsed = min(elapsed_times) if elapsed_times else 0

        fallback_count = sum(1 for e in self.turn_log if e.get("used_fallback"))
        exception_count = len(self.errors)
        quality_issue_count = len(self.quality_issues)

        # Category breakdown
        category_counts: Counter[str] = Counter(e["category"] for e in self.turn_log)

        # Issue types
        all_issue_types: Counter[str] = Counter()
        for qi in self.quality_issues:
            for issue in qi.get("issues", []):
                kind = issue.split(":")[0].strip()
                all_issue_types[kind] += 1
        for e in self.errors:
            all_issue_types["EXCEPTION"] += 1

        # Overall pass/fail
        critical_issues = exception_count + sum(1 for qi in self.quality_issues
                                                 for i in qi.get("issues", [])
                                                 if "EXCEPTION" in i or "EMPTY_RESPONSE" in i
                                                 or "model broke character" in i)
        passed = critical_issues == 0 and completed >= self.args.turns * 0.95

        lines: list[str] = []
        sep = "=" * 72

        def h(title: str) -> None:
            lines.extend(["", sep, f"  {title}", sep])

        lines.append("MØRKYN AUTOMATED PLAYTEST REPORT")
        lines.append(f"Generated : {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Duration  : {duration:.0f}s ({duration/60:.1f} min)")
        lines.append(f"Model     : {self.model}  [MLE]")
        lines.append(f"DB path   : {self.db_path}")

        h("SUMMARY")
        lines.append(f"  Turns requested   : {self.args.turns}")
        lines.append(f"  Turns completed   : {completed}")
        lines.append(f"  Completion rate   : {completed / self.args.turns * 100:.1f}%")
        lines.append(f"  Exceptions (crash): {exception_count}")
        lines.append(f"  Fallback turns    : {fallback_count}")
        lines.append(f"  Quality issues    : {quality_issue_count}")
        lines.append(f"  Avg turn time     : {avg_elapsed:.1f}s")
        lines.append(f"  Min / Max time    : {min_elapsed:.1f}s / {max_elapsed:.1f}s")
        lines.append("")
        lines.append(f"  OVERALL: {'✓ PASS' if passed else '✗ FAIL'}")

        h("MLE")
        lines.append(f"  model: {self.model}")
        lines.append("  The welding rig is not connected yet, so a local turn says so.")

        h("TURN CATEGORY BREAKDOWN")
        for cat, count in sorted(category_counts.items()):
            lines.append(f"  {cat:12s}: {count:3d} turns")

        h("ISSUE TYPE SUMMARY")
        if all_issue_types:
            for issue_type, count in all_issue_types.most_common():
                lines.append(f"  {issue_type:35s}: {count}")
        else:
            lines.append("  No issues detected.")

        if self.errors:
            h("EXCEPTIONS (CRASHES)")
            for e in self.errors:
                lines.append(f"\n  Turn {e['turn']:3d}  [{e.get('category', '?'):7s}]")
                lines.append(f"  Input    : {e['input']}")
                lines.append(f"  Error    : {e['error']}")
                tb_lines = e.get("traceback", "").strip().splitlines()
                # Include last 8 lines of traceback
                for tb_line in tb_lines[-8:]:
                    lines.append(f"             {tb_line}")
        else:
            h("EXCEPTIONS (CRASHES)")
            lines.append("  None — all turns completed without Python exceptions.")

        if self.quality_issues:
            h("LLM QUALITY ISSUES (turn-by-turn)")
            for qi in self.quality_issues:
                lines.append(f"\n  Turn {qi['turn']:3d}  [{qi.get('category','?'):7s}]")
                lines.append(f"  Input   : {qi['input']}")
                for issue in qi["issues"]:
                    lines.append(f"  Issue   : {issue}")
                snip = qi.get("narration_snippet", "")
                if snip:
                    lines.append(f"  Snippet : {snip!r}")
        else:
            h("LLM QUALITY ISSUES")
            lines.append("  No quality issues detected in narration.")

        h("LLM RESPONSE QUALITY NOTES")
        # Repetition ratio
        rep_count = sum(1 for qi in self.quality_issues
                        for i in qi.get("issues", []) if "REPETITION" in i)
        empty_count = sum(1 for qi in self.quality_issues
                          for i in qi.get("issues", []) if "EMPTY" in i)
        short_count = sum(1 for qi in self.quality_issues
                          for i in qi.get("issues", []) if "SHORT" in i)
        char_break = sum(1 for qi in self.quality_issues
                         for i in qi.get("issues", []) if "broke character" in i)

        narration_lens = [e["narration_len"] for e in self.turn_log if e.get("narration_len", 0) > 0]
        avg_narr = sum(narration_lens) / len(narration_lens) if narration_lens else 0

        lines.append(f"  Avg narration length     : {avg_narr:.0f} chars")
        lines.append(f"  Empty/missing responses  : {empty_count}")
        lines.append(f"  Short responses (<40ch)  : {short_count}")
        lines.append(f"  High repetition turns    : {rep_count}")
        lines.append(f"  Character breaks         : {char_break}")
        lines.append(f"  Fallback turns           : {fallback_count}")

        if fallback_count > self.args.turns * 0.2:
            lines.append("  ⚠  HIGH FALLBACK RATE — LLM may be returning malformed JSON frequently.")
        if rep_count > 5:
            lines.append("  ⚠  REPETITION — model may be looping on context or ignoring variety.")
        if char_break > 0:
            lines.append("  ⚠  CHARACTER BREAKS — model is leaking its AI identity into narration.")
        if avg_narr < 80:
            lines.append("  ⚠  VERY SHORT NARRATIONS — responses may be truncated or model is too small.")

        h("FULL TURN LOG")
        lines.append(f"  {'Turn':>4}  {'Cat':7}  {'Chars':>6}  {'Time':>5}  {'Fallback'}  Input")
        lines.append(f"  {'-'*4}  {'-'*7}  {'-'*6}  {'-'*5}  {'-'*8}  {'-'*40}")
        for entry in self.turn_log:
            has_issues = "⚠ " if entry.get("errors") else "  "
            fb = "yes" if entry.get("used_fallback") else "no"
            input_preview = entry.get("input", "")[:42]
            lines.append(
                f"  {entry['turn']:4d}  {entry.get('category','?'):7s}  "
                f"{entry.get('narration_len', 0):6d}  "
                f"{entry.get('elapsed', 0):4.1f}s  "
                f"{has_issues}{fb:3s}      {input_preview!r}"
            )

        h("PASS / FAIL VERDICT")
        if passed:
            lines.append("  ✓ PASS")
            lines.append("  The playtest completed without critical failures.")
        else:
            lines.append("  ✗ FAIL")
            reasons = []
            if exception_count > 0:
                reasons.append(f"{exception_count} Python exception(s)")
            if completed < self.args.turns * 0.95:
                reasons.append(f"only {completed}/{self.args.turns} turns completed")
            if char_break > 0:
                reasons.append(f"{char_break} character-break(s) detected")
            if empty_count > 3:
                reasons.append(f"{empty_count} empty responses")
            for r in reasons:
                lines.append(f"  • {r}")

        lines.append("")
        lines.append(sep)
        lines.append("  End of report")
        lines.append(sep)

        report_text = "\n".join(lines)
        report_path.write_text(report_text, encoding="utf-8")
        print(f"\n[REPORT] Written to: {report_path.resolve()}")
        # Also print summary to stdout
        print("\n" + "\n".join(lines[:30]))


# ──────────────────────────────────────────────────────────────────────────────
# 7.  Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()
    print("=" * 72)
    print("  MØRKYN AUTOMATED PLAYTEST HARNESS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    run = PlaytestRun(args)
    print(f"\n[MODEL] MLE model name: {run.model}")
    print("[MODEL] The welding rig is not connected yet. Local turns will say so.")
    print()

    run.run()
