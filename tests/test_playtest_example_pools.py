"""Example pools (playtest #14 prompt side, #26, and the user's direction).

Fixed example lists were pasted: two games opened with "Aria the baker", two
characters were "Miriam Shaw", and a setup face came back "amber eyes ...
faint scar on right cheek" from a contract example. Examples stay, but each
call draws three to five fresh ones from large world-filtered pools, names a
world has used are never drawn again, recent player names are avoided across
games, and hard appearance values are rolled by the engine.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-example-pools-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, example_pools as ep, llm, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.setup_composer import FIELD_CONTRACTS  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT, build_dsl_user_prompt  # noqa: E402

MEDIEVAL = {"world_style": "frontier dark fantasy", "tech_level": "medieval", "magic_level": "rare"}
CYBERPUNK = {"world_style": "cyberpunk megacity", "tech_level": "", "magic_level": "none"}
COASTAL = {"world_style": "coastal fantasy harbour towns", "tech_level": "medieval", "magic_level": "common utility"}
XIANXIA = {"world_style": "xianxia cultivation sect politics", "tech_level": "medieval", "magic_level": "cultivation"}
STEAM = {"world_style": "gaslight steam city", "tech_level": "early industrial", "magic_level": "rare"}
VILLAGE = {"name": "Eldoria's Edge", "summary": "a frontier village", "settlement_size": "village"}
HARBOUR = {"name": "Saltmouth Harbour", "summary": "a harbour town with docks", "settlement_size": "town"}
MARKET = {"name": "Sublevel 9 Market", "summary": "a neon market under the arcology", "settlement_size": "city"}


def _capture_prompt(group: str, current: dict) -> dict:
    captured: dict = {}

    def fake_chat(system, user, **kwargs):
        captured.setdefault("user", user)
        raise RuntimeError("stop after prompt build")

    original = llm._chat_json
    llm._chat_json = fake_chat
    try:
        llm.generate_setup_randomization(group, current)
    except Exception:
        pass
    finally:
        llm._chat_json = original
    return json.loads(captured["user"])


class DrawsAreSeededAndFiltered(unittest.TestCase):
    def test_a_seeded_rng_gives_the_same_draw(self):
        ctx = ep.world_context(MEDIEVAL, location=VILLAGE)
        for kind in ep.KINDS:
            with self.subTest(kind=kind):
                one = ep.draw(kind, {**ctx, "races": "human, elf"}, 4, random.Random(11))
                two = ep.draw(kind, {**ctx, "races": "human, elf"}, 4, random.Random(11))
                self.assertEqual(one, two)
                self.assertTrue(one, kind)

    def test_no_modern_clothes_in_a_medieval_world(self):
        ctx = ep.setup_context(MEDIEVAL)
        rng = random.Random(3)
        blob = " ".join(" ".join(ep.draw(k, ctx, 5, rng)) for k in ("appearance", "starter_equipment") for _ in range(60)).lower()
        for word in ("sneakers", "hoodie", "jeans", "phone", "backpack", "mag-soled"):
            self.assertNotIn(word, blob)

    def test_no_net_mender_inland_or_in_cyberpunk(self):
        rng = random.Random(5)
        inland = ep.world_context(MEDIEVAL, location=VILLAGE)
        neon = ep.world_context(CYBERPUNK, location=MARKET)
        for ctx in (inland, neon):
            drawn = [job for _ in range(200) for job in ep.draw("npc_role", ctx, 5, rng)]
            for job in ("net mender", "ferryman", "boatwright", "eel fisher", "dock hand"):
                self.assertNotIn(job, drawn)
        harbour = ep.world_context(COASTAL, location=HARBOUR)
        drawn = {job for _ in range(200) for job in ep.draw("npc_role", harbour, 5, rng)}
        self.assertIn("net mender", drawn)
        # A harbour town still has its bakers.
        self.assertTrue(drawn & {"baker", "potter", "miller", "carter"})

    def test_names_follow_the_world_and_the_sex(self):
        rng = random.Random(9)
        xianxia = ep.world_context(XIANXIA)
        self.assertEqual(xianxia["culture"], "chinese")
        female = ep.draw_names(ep.world_context(MEDIEVAL), 5, rng, sex="female")
        common = ep._NAMES["common"]
        for name in female:
            self.assertIn(name.split()[0], common["female"])

    def test_hard_values_are_rolled_by_the_engine_and_kept(self):
        ctx = ep.setup_context(MEDIEVAL)
        rolled = ep.roll_values("facial_features", ctx, random.Random(2))
        self.assertIn("eye_colour", rolled)
        out = ep.apply_rolled_values("facial_features", "high cheekbones, a crooked smile", rolled)
        self.assertIn(rolled["eye_colour"], out)
        if rolled["notable_mark"] != "none":
            self.assertIn(rolled["notable_mark"], out)
        hair = ep.roll_values("hair", ctx, random.Random(4))
        kept = ep.apply_rolled_values("hair", "worn in a loose braid", hair)
        self.assertIn(hair["hair_colour"], kept)


class DistributionIsWide(unittest.TestCase):
    """300 draws per kind across five world types: many distinct, no favourite."""

    WORLDS = ((MEDIEVAL, VILLAGE), (COASTAL, HARBOUR), (CYBERPUNK, MARKET), (XIANXIA, VILLAGE), (STEAM, VILLAGE))
    FLOORS = {"person_name": 200, "npc_role": 20, "venue_name": 150, "hair": 150, "facial_features": 200,
              "appearance": 200, "economy": 15, "quest_style": 15, "faction_pressure": 10}

    def test_distinct_counts_and_top_share(self):
        for opts, loc in self.WORLDS:
            ctx = ep.world_context(opts, location=loc)
            for kind, floor in self.FLOORS.items():
                with self.subTest(world=opts["world_style"], kind=kind):
                    rng = random.Random(f"{kind}|{opts['world_style']}")
                    counts = Counter(item for _ in range(300) for item in ep.draw(kind, ctx, 1, rng))
                    self.assertGreaterEqual(len(counts), floor)
                    self.assertLessEqual(counts.most_common(1)[0][1] / 300, 0.12)


class UsedNamesAreNotDrawnAgain(unittest.TestCase):
    def setUp(self):
        db.init_db()
        world.start_playthrough({"player_name": "Miriam Shaw", "start_location": "Eldoria's Edge", "special_ability_origin": "none"})

    def test_a_created_npc_is_recorded_and_excluded(self):
        with connect() as conn:
            loc = conn.execute("SELECT id FROM locations LIMIT 1").fetchone()[0]
            world._upsert_npc(conn, {"name": "Hawise Pollard", "role": "baker", "location_id": loc})
            ledger = [r[0] for r in conn.execute("SELECT name FROM name_ledger").fetchall()]
            self.assertIn("Hawise Pollard", ledger)
            used = ep.used_names(conn) + ep.recent_player_names(conn)
        ctx = ep.world_context(MEDIEVAL, location=VILLAGE)
        drawn = [n for i in range(300) for n in ep.draw_names(ctx, 5, random.Random(i), used)]
        tokens = {part for name in drawn for part in name.lower().split()}
        for part in ("hawise", "pollard", "miriam", "shaw"):
            self.assertNotIn(part, tokens)

    def test_player_names_are_avoided_in_the_next_game(self):
        world.start_playthrough({"player_name": "Odelia Venn", "start_location": "Low Gate", "special_ability_origin": "none"})
        recent = ep.recent_player_names()
        self.assertEqual(recent[0], "Odelia Venn")
        self.assertIn("Miriam Shaw", recent)
        prompt = _capture_prompt("field:player_name", {"player_sex": "female", **MEDIEVAL})
        self.assertIn("Miriam Shaw", prompt.get("avoid_names") or [])
        for option in prompt.get("name_options") or []:
            self.assertNotIn("Odelia", option)
            self.assertNotIn("Shaw", option)

    def test_the_draft_prompt_carries_fresh_cast_options(self):
        state = world.get_state()
        state.setdefault("settings", {}).setdefault("playthrough_options", {}).update(MEDIEVAL)
        context = world.build_prompt_context(state, "I look around.")
        cast = context.get("cast_options") or {}
        self.assertTrue(3 <= len(cast.get("names") or []) <= 5, cast)
        self.assertTrue(cast.get("jobs"))
        packet = json.loads(build_dsl_user_prompt(context, "I look around."))
        self.assertEqual(packet["cast_options"]["names"], cast["names"])
        self.assertIn("cast_options.names", DSL_SYSTEM_PROMPT)


class PromptsShipDrawsNotAFixedList(unittest.TestCase):
    def test_no_contract_carries_a_fixed_example_list(self):
        for field, contract in FIELD_CONTRACTS.items():
            self.assertNotIn("examples", contract, field)

    def test_two_builds_show_different_examples(self):
        for field in ("facial_features", "hair", "economy", "quest_style", "appearance"):
            with self.subTest(field=field):
                prompts = [_capture_prompt(f"field:{field}", dict(MEDIEVAL)) for _ in range(3)]
                lines = [
                    next((r for r in p["rules"] if r.startswith(ep.EXAMPLES_RULE)), "") for p in prompts
                ]
                self.assertTrue(all(lines), field)
                self.assertGreater(len(set(lines)), 1, lines)

    def test_the_logged_face_example_is_gone(self):
        prompt = _capture_prompt("field:facial_features", dict(MEDIEVAL))
        blob = json.dumps(prompt).lower()
        self.assertNotIn("amber eyes, high cheekbones, crooked smile", blob)
        rolled = prompt.get("engine_rolled") or {}
        self.assertIn("eye_colour", rolled)
        self.assertIn(rolled["eye_colour"], " ".join(p for p in prompt["rules"] if p.startswith(ep.EXAMPLES_RULE)))

    def test_the_group_path_carries_the_rolls(self):
        contracts = llm._field_contracts_for_prompt(
            ["hair", "facial_features"], dict(MEDIEVAL), set(), {"hair": {"hair_colour": "auburn", "hair_length": "long"}}
        )
        self.assertEqual(contracts["hair"]["engine_rolled"]["hair_colour"], "auburn")
        self.assertNotIn("engine_rolled", contracts["facial_features"])


if __name__ == "__main__":
    unittest.main()
