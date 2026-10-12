"""Two-part ability growth end to end: model seed -> engine growth at setup, Start, and every use.

The model is mocked; the database is a temporary file pinned through the AI_RPG_* env.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-ability-growth-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(_ENV)

from app import ability_growth, llm, world  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402
from app.player_resources import ability_use_prompt_block, apply_ability_use  # noqa: E402


def setUpModule() -> None:
    os.environ.update(_ENV)
    assert str(db_path()).startswith(str(_TMP)), f"test isolation failed: {db_path()!r}"
    init_db()


MODEL_ANSWER = {
    "special_abilities": [
        {
            "name": "Ledger of Small Debts",
            "description": "Touch a coin and know the last hand that spent it; one coin per scene.",
            "locked": False,
            "prerequisites": "",
            "cost": "A dull headache for the rest of the scene",
            "power_type": "compounding",
            "growth": {"pace": "fast", "start": "weak", "grows": "how many hands back the coin remembers"},
        },
        {
            # An 8B habit: the old stock math pasted in, no seed. The engine must replace it.
            "name": "Salt Lantern",
            "description": "Make a pinch of salt glow for ten minutes, enough to read a face.",
            "locked": False,
            "prerequisites": "",
            "cost": "Burns the salt and numbs the fingertips",
            "growth_math": "OP seed: F→E@60 E→D@140 D→C@320; use 6-14 XP × risk; XP_to_next = 40 * rank_index^1.55",
            "power_type": "linear",
        },
    ]
}


def _current():
    return {
        "_locked_fields": [],
        "_field_context": {"count_min": 2, "count_max": 2, "requested_count": 2, "target_count": 2, "count_rolled": True},
        "world_style": "salt marsh frontier",
        "magic_level": "rare",
        "difficulty": "hard",
        "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
        "special_abilities": [],
    }


class GenerationTests(unittest.TestCase):
    def test_every_ability_leaves_with_engine_math(self):
        phases: list[str] = []

        def fake_chat(*args, **kwargs):
            phases.append(str(kwargs.get("phase") or ""))
            return MODEL_ANSWER

        with mock.patch.object(llm, "_chat_json", side_effect=fake_chat):
            result = llm.generate_setup_randomization("field:special_abilities", _current())
        abilities = result["special_abilities"]
        self.assertEqual(len(abilities), 2)
        for ab in abilities:
            with self.subTest(ability=ab["name"]):
                self.assertIsInstance(ab.get("growth"), dict)
                expected = ability_growth.build(ab, rank_scale="F,E,D,C,B,A,S,SS,SSS", difficulty="hard")
                self.assertEqual(ab["growth_math"], expected["growth_math"])
                self.assertNotIn("@60", ab["growth_math"])
        ledger = next(a for a in abilities if a["name"] == "Ledger of Small Debts")
        self.assertEqual(ledger["growth"], {"template": "compounding", "pace": "fast", "start": "weak",
                                            "grows": "how many hands back the coin remembers"})
        self.assertNotIn("setup_ability_growth_math_optimize", phases, "no model call is spent rewriting math")

    def test_clone_costs_are_repaired_not_retried(self):
        """The 8B trace: three good cards, one shared meditation-hour cost, a batch denial, a retry
        the model answered by echoing the prompt, and seed-pool cards labelled as the model's."""
        same_cost = "Once per day; 1 hour of meditation to recharge after use"
        answer = {"special_abilities": [
            {"name": "Veil of Silent Debt", "description": "Touch a creditor's ledger to make them forget one debt you owe for an hour.",
             "cost": same_cost, "power_type": "compounding", "growth": {"pace": "steady", "start": "weak"}},
            {"name": "Frost's Whisper", "description": "Chill a cup of water to ice with a breath; one cup at a time.",
             "cost": same_cost, "power_type": "linear", "growth": {"pace": "fast"}},
            {"name": "Lens of Unwilling Eyes", "description": "See through one closed eyelid for a few seconds.",
             "cost": same_cost, "power_type": "passive", "growth": {"pace": "slow"}},
        ]}
        phases: list[str] = []

        def fake_chat(*args, **kwargs):
            phases.append(str(kwargs.get("phase") or ""))
            return answer

        current = {**_current(), "_field_context": {"count_min": 3, "count_max": 3, "requested_count": 3,
                                                    "target_count": 3, "count_rolled": True}}
        with mock.patch.object(llm, "_chat_json", side_effect=fake_chat):
            result = llm.generate_setup_randomization("field:special_abilities", current)
        names = [a["name"] for a in result["special_abilities"]]
        self.assertEqual(sorted(names), sorted(a["name"] for a in answer["special_abilities"]))
        self.assertNotIn("setup_randomize_abilities_quality_retry", phases)
        self.assertFalse(result.get("fallback_used"))
        self.assertGreater(len({a["cost"] for a in result["special_abilities"]}), 1, "the clone costs were broken up")

    def test_an_echoed_retry_keeps_the_models_cards(self):
        bad_then_echo = [
            {"special_abilities": [{"name": "A", "description": "x"}, {"name": "A", "description": "x"}]},
        ]

        def fake_chat(*args, **kwargs):
            if kwargs.get("phase") == "setup_randomize_abilities_quality_retry":
                return {"task": "echo", "denial_summary": [], "failed_reports": []}
            return MODEL_ANSWER

        with mock.patch.object(llm, "_chat_json", side_effect=fake_chat):
            result = llm.generate_setup_randomization("field:special_abilities", _current())
        names = {a["name"] for a in result["special_abilities"]}
        self.assertTrue(names & {"Ledger of Small Debts", "Salt Lantern"}, names)

    def test_the_prompt_no_longer_shows_stock_math(self):
        prompts: list[str] = []

        def fake_chat(system, user, **kwargs):
            prompts.append(user)
            return MODEL_ANSWER

        with mock.patch.object(llm, "_chat_json", side_effect=fake_chat):
            llm.generate_setup_randomization("field:special_abilities", _current())
        first = prompts[0]
        for sample in llm.GROWTH_MATH_SAMPLES:
            self.assertNotIn(sample[:40], first)
        self.assertIn("growth_seed_contract", first)


class StartAndUseTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.update(_ENV)
        world.start_playthrough({
            "player_name": "Wren", "start_location": "Low Gate", "special_ability_origin": "both",
            "magic_level": "rare", "difficulty": "normal", "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
            "special_abilities": [
                {"name": "Ledger of Small Debts", "description": "Touch a coin and know who last spent it.",
                 "locked": False, "cost": "", "power_type": "compounding",
                 "growth": {"pace": "steady", "start": "weak", "grows": "how far back"}},
                {"name": "Tidecall", "description": "Call the tide a hand higher for a minute.",
                 "locked": True, "prerequisites": "Swear an oath to the sea", "cost": "", "power_type": "breakthrough"},
            ],
        })

    def _row(self, name: str) -> dict:
        with connect() as conn:
            return dict(conn.execute("SELECT * FROM abilities WHERE name = ?", (name,)).fetchone())

    def test_start_stores_engine_growth_and_keeps_the_cards_lock(self):
        ledger, tide = self._row("Ledger of Small Debts"), self._row("Tidecall")
        spec = json.loads(ledger["growth"])
        self.assertEqual(spec["template"], "compounding")
        self.assertEqual(json.loads(ledger["growth_state"])["index"], 0)
        self.assertEqual(ledger["power_type"], "compounding")
        self.assertEqual(ledger["growth_math"], ability_growth.render_text(spec))
        self.assertEqual(ledger["locked"], 0, "the seed power stays usable at Start")
        self.assertEqual(tide["locked"], 1, "a card marked 'needs unlock' stays locked")
        self.assertEqual(json.loads(tide["growth"])["template"], "breakthrough")

    def test_using_an_ability_advances_it(self):
        with connect() as conn:
            ab = dict(conn.execute("SELECT * FROM abilities WHERE name = ?", ("Ledger of Small Debts",)).fetchone())
            packs = []
            for i in range(40):
                packs.append(apply_ability_use(conn, ab, options={"magic_level": "rare"},
                                               world_time={"day": 1 + i, "minute": 0}, turn=i + 1, risk=2))
            conn.commit()
        # Energy runs out without rest (no turns pass here); a blocked use earns nothing.
        done = [p for p in packs if p["ok"]]
        self.assertGreaterEqual(len(done), 5)
        self.assertTrue(all("growth" not in p for p in packs if not p["ok"]))
        state = json.loads(self._row("Ledger of Small Debts")["growth_state"])
        self.assertEqual(state["uses"], len(done))
        self.assertGreater(state["index"], 0)
        ups = [e for p in done for e in p["growth"]["events"] if e["type"] == "rank_up"]
        self.assertEqual(len(ups), state["index"])
        block = ability_use_prompt_block(next(p for p in done if p["growth"]["events"]))
        self.assertIn("Growth (engine)", block)
        self.assertIn("RANK UP", block)

    def test_risk_earns_more_xp(self):
        with connect() as conn:
            ab = dict(conn.execute("SELECT * FROM abilities WHERE name = ?", ("Ledger of Small Debts",)).fetchone())
            safe = apply_ability_use(conn, ab, options={}, world_time={"day": 1, "minute": 0}, turn=1, risk=1)
            risky = apply_ability_use(conn, ab, options={}, world_time={"day": 2, "minute": 0}, turn=1, risk=4)
        self.assertGreater(risky["growth"]["xp_gained"], safe["growth"]["xp_gained"])

    def test_the_game_state_shows_growth_now_not_the_spec(self):
        with connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM abilities").fetchall()]
        shown = world._abilities_with_growth_now(rows)
        ledger = next(a for a in shown if a["name"] == "Ledger of Small Debts")
        self.assertNotIn("growth", ledger)
        self.assertEqual(ledger["rank"], "F")
        self.assertIn("rank F", ledger["growth_now"])


class RequestModelTests(unittest.TestCase):
    def test_the_web_request_keeps_power_type_and_seed(self):
        from app.main import SetupRequest

        req = SetupRequest(special_abilities=[{"name": "Ledger", "description": "x", "power_type": "compounding",
                                               "growth": {"pace": "fast"}}])
        dumped = req.special_abilities[0].model_dump()
        self.assertEqual(dumped["power_type"], "compounding")
        self.assertEqual(dumped["growth"], {"pace": "fast"})


if __name__ == "__main__":
    unittest.main()
