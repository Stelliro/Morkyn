"""Tests for app/scene_cast.py (TODO n14, built but not wired).

Every function under test is pure: the temporary database exists only because the app modules this
module imports read the AI_RPG_* paths at import, and one test proves nothing here opens it. No model,
no network, no wall clock; names are drawn from explicit pools or stable seeds.

Run:  python -m unittest tests.test_scene_cast
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-scene-cast-leaf-test-"))
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

from app.db import connect, db_path, init_db  # noqa: E402
from app import scene_cast  # noqa: E402
from app.turn_dsl import parse_dsl_turn, parse_ops_detailed  # noqa: E402


def setUpModule() -> None:
    os.environ.update(_ENV)
    assert str(db_path()).startswith(str(_TMP)), f"test isolation failed: {db_path()!r}"
    init_db()
    conn = connect()
    try:
        with conn:
            scene_cast.ensure_schema(conn)
    finally:
        conn.close()


# contracts.md 1: the shared shapes this module produces.
_EVIDENCE_TYPES = {"check": str, "ok": bool, "evidence": str, "severity": str, "weight": float}
_ENTITY_REF_TYPES = {"code": str, "name": str, "kind": str, "role": str}
_NPC_ROW_KEYS = (
    "code", "name", "race", "location", "role", "summary", "attitude", "personality", "likes", "principles",
    "dislikes", "rank", "stat_profile", "skill_profile", "trust_delta", "known_fact", "mentioned_by",
)


def _assert_shape(case: unittest.TestCase, row: dict, types: dict) -> None:
    for key, kind in types.items():
        case.assertIn(key, row)
        case.assertIsInstance(row[key], kind, f"{key} is {type(row[key]).__name__}, not {kind.__name__}")


def _context(**overrides) -> dict:
    """A handed-off context: the inn (here) with Mara and Dorn, a market square, a coat, a rope, an event."""
    npcs = [
        {"id": 1, "code": "A", "name": "Mara", "role": "innkeeper", "pronouns": "she", "presence": "full", "workplace_id": 1},
        {"id": 2, "code": "B", "name": "Dorn", "role": "guard captain", "pronouns": "he", "presence": "event_worthy"},
    ]
    ctx = {
        "current_location": {"id": 1, "code": "L1", "name": "Second Shadow Inn", "npcs": copy.deepcopy(npcs), "exit_to": "Market Square"},
        "locations": [
            {"id": 1, "code": "L1", "name": "Second Shadow Inn", "npcs": copy.deepcopy(npcs)},
            {"id": 2, "code": "L2", "name": "Market Square", "npcs": [{"id": 5, "code": "E", "name": "Wren", "role": "peddler"}]},
        ],
        "inventory": [
            {"id": 3, "code": "I3", "name": "travel-stained coat", "equipped_slot": "body"},
            {"id": 4, "code": "I4", "name": "rope"},
        ],
        "events": [{"code": "E1", "title": "The Ford Rising"}],
        "cast_options": {"names": ["Tamsin", "Bram"], "jobs": ["broker", "carter"]},
        "conversation_turn": {"addressed": [], "speech": False},
        "settings": {"active_scene": {"present": [], "interacting": []}},
        "turn_plan": {"primary_intent": "general", "explicit_references": {"all": []}},
    }
    ctx.update(overrides)
    return ctx


def _involved(ctx: dict, line: str = "I nod to Mara.", **kw) -> dict:
    return scene_cast.build_involved(ctx, line, turn=kw.pop("turn", 3), **kw)["involved"]


def _turn(narration: str, ops: str = "", player_input: str = "I nod.") -> dict:
    return parse_dsl_turn(f"===NAR===\n{narration}\n===OPS===\n{ops}\n", player_input)


_LONG = " ".join(["The common room hums with low talk and the smell of wet wool."] * 6)


class LeafTests(unittest.TestCase):
    def test_module_is_a_leaf(self):
        module = ROOT / "app" / "scene_cast.py"
        source = module.read_text(encoding="utf-8")
        for line in ("Status: built, not wired (TODO n14).", "Wiring (not done):", "Turn on:", "Tests: tests/test_scene_cast.py"):
            self.assertIn(line, source)
        for private in ("_entity_code_name_map", "_entity_code_role_map", "_repair_gear_as_agent_prose", "unique_person_name", "app.db", "connect("):
            self.assertNotIn(private, source, f"scene_cast must not name {private}")
        hits = subprocess.run(
            ["grep", "-rln", "--exclude-dir=__pycache__", r"app\.scene_cast\|scene_cast\.\(build_involved\|bind\|verify\)\|from app import scene_cast", "app", "static"],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout.split()
        self.assertEqual([h for h in hits if not h.endswith("app/scene_cast.py")], [], hits)

    def test_private_imports_still_exist(self):
        from app import world

        for name in ("_figure_hints", "_is_place_or_item_code", "_turn_intent", "is_plausible_person_name", "is_generic_person_label", "invent_person_name", "name_seed"):
            self.assertTrue(callable(getattr(world, name)), name)

    def test_ensure_schema_is_a_no_op(self):
        conn = connect()
        try:
            before = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            with conn:
                scene_cast.ensure_schema(conn)
            after = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            conn.close()
        self.assertEqual(before, after)

    def test_no_db_access(self):
        import app.db as app_db

        ctx = _context()
        em = scene_cast.entity_map_from_context(ctx)
        inv = _involved(ctx)
        turn = _turn(f"{{NPC_1}} nods. {{NPC_9}} waves. {_LONG}")
        with mock.patch.dict(os.environ, {"AI_RPG_DB": str(_TMP / "missing" / "nope.db")}):
            with mock.patch.object(app_db, "connect", side_effect=AssertionError("scene_cast opened the database")):
                b = scene_cast.bind(turn, inv, em, seed=4)
                v = scene_cast.verify(b["turn"], inv, b["binding"], em)
                scene_cast.propose_repairs(b["turn"], v, b["binding"], em, seed=4)
        self.assertFalse(v["ok"])

    def test_no_foreign_writes(self):
        conn = connect()
        try:
            with conn:
                conn.execute("INSERT INTO player (id, name, health, max_health, level, xp, gold, current_location_id) VALUES (1, 'T', 20, 20, 1, 0, 12, NULL) ON CONFLICT(id) DO NOTHING")
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]

            def counts() -> dict:
                return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}

            before = counts()
            ctx = _context()
            em = scene_cast.entity_map_from_context(ctx)
            inv = _involved(ctx, "I ask someone the way")
            b = scene_cast.bind(_turn("{NPC_1} nods. {NPC_3} grins. " + _LONG), inv, em)
            v = scene_cast.verify(b["turn"], inv, b["binding"], em)
            plan = scene_cast.propose_repairs(b["turn"], v, b["binding"], em)
            scene_cast.apply_repairs(b["turn"], plan)
            with conn:
                scene_cast.ensure_schema(conn)
            self.assertEqual(before, counts())
        finally:
            conn.close()


class EntityMapTests(unittest.TestCase):
    def test_entity_map_from_context_kinds_and_flags(self):
        em = scene_cast.entity_map_from_context(_context())
        self.assertEqual({p["kind"] for p in em["people"]}, {"person"})
        mara = em["by_code"]["A"]
        _assert_shape(self, mara, _ENTITY_REF_TYPES)
        self.assertEqual((mara["pronouns"], mara["here"], mara["role"]), ("she", True, "innkeeper"))
        self.assertEqual(em["by_code"]["B"]["pronouns"], "he")
        self.assertFalse(em["by_code"]["E"]["here"])
        self.assertTrue(em["by_code"]["L1"]["here"])
        self.assertFalse(em["by_code"]["L2"]["here"])
        self.assertEqual(em["by_code"]["L2"]["kind"], "place")
        self.assertTrue(em["by_code"]["I3"]["worn"])
        self.assertFalse(em["by_code"]["I4"]["worn"])
        self.assertEqual(em["by_code"]["E1"]["kind"], "event")
        self.assertIs(em["names_lower"]["mara"], mara)
        self.assertEqual(em["names_lower"]["second shadow inn"]["code"], "L1")
        for ref in em["people"] + em["places"] + em["items"] + em["events"]:
            _assert_shape(self, ref, _ENTITY_REF_TYPES)
            self.assertIn(ref["kind"], ("person", "place", "item", "event"))
            self.assertTrue(ref["name"])

    def test_entity_map_from_rows_matches_from_context(self):
        ctx = _context()
        from_ctx = scene_cast.entity_map_from_context(ctx)
        people = [dict(n, here=True) for n in ctx["locations"][0]["npcs"]] + [dict(n, here=False) for n in ctx["locations"][1]["npcs"]]
        places = [dict(ctx["current_location"], here=True), dict(ctx["locations"][1], here=False)]
        from_rows = scene_cast.entity_map_from_rows(people, places, ctx["inventory"], [{"code": "E1", "title": "The Ford Rising"}])
        self.assertEqual(from_rows["by_code"], from_ctx["by_code"])


class BuildInvolvedTests(unittest.TestCase):
    def test_build_involved_addressed_first_and_must_speak(self):
        ctx = _context(conversation_turn={"addressed": ["B"], "speech": True})
        inv = _involved(ctx, "I ask Dorn about the road.")
        self.assertEqual([(n["slot"], n["code"], n["source"], n["must_speak"]) for n in inv["npcs"]], [("NPC_1", "B", "addressed", True), ("NPC_2", "A", "keeper", False)])

    def test_build_involved_companion_keeper_scene_order(self):
        npcs = [
            {"id": 1, "code": "A", "name": "Mara", "role": "innkeeper", "pronouns": "she", "presence": "background"},
            {"id": 2, "code": "B", "name": "Dorn", "role": "guard captain", "presence": "full"},
            {"id": 3, "code": "C", "name": "Ilse", "role": "scout", "presence": "full"},
            {"id": 4, "code": "D", "name": "Keeper Ott", "role": "keeper", "presence": "full", "workplace_id": 1},
            {"id": 5, "code": "E", "name": "Pell", "role": "patron", "presence": "nameless"},
        ]
        ctx = _context()
        ctx["current_location"]["npcs"] = copy.deepcopy(npcs)
        ctx["current_location"]["keeper"] = {"code": "D", "name": "Keeper Ott", "role": "keeper"}
        ctx["locations"][0]["npcs"] = copy.deepcopy(npcs)
        ctx["scene_thread"] = {"with": [{"code": "C", "name": "Ilse"}]}
        ctx["settings"] = {"active_scene": {"present": ["E"], "interacting": []}}
        out = scene_cast.build_involved(ctx, "I look around.", turn=3)
        inv = out["involved"]
        self.assertEqual([n["code"] for n in inv["npcs"]], ["C", "D", "E", "B"])
        self.assertEqual([n["source"] for n in inv["npcs"]], ["companion", "keeper", "present", "here"])
        self.assertEqual(inv["limits"]["npcs"], 4)
        self.assertTrue(any(note.startswith("left out: Mara") for note in out["notes"]), out["notes"])

    def test_build_involved_new_face_triggers_and_limit(self):
        empty = _context(turn_plan={"primary_intent": "conversation", "explicit_references": {"all": []}})
        empty["current_location"]["npcs"] = []
        empty["locations"][0]["npcs"] = []
        out = scene_cast.build_involved(empty, "I ask someone the way to the ford.", turn=3)
        inv = out["involved"]
        self.assertEqual([(n["slot"], n["status"], n["name"], n["code"]) for n in inv["npcs"]], [("NPC_1", "new", "Tamsin", None)])
        self.assertEqual(inv["npcs"][0]["role_hint"], "broker")
        self.assertTrue(any("new face" in n for n in out["notes"]))
        opening = scene_cast.build_involved(empty, "__opening_scene_request__", turn=0, input_kind="opening")["involved"]
        self.assertEqual([n["status"] for n in opening["npcs"]], ["new", "new"])
        self.assertEqual(opening["limits"], scene_cast.LIMITS_OPENING)
        crowded = _context()
        crowd = [{"id": 10 + i, "code": c, "name": n, "role": "patron", "presence": "full"} for i, (c, n) in enumerate([("A", "Mara"), ("B", "Dorn"), ("C", "Ilse"), ("D", "Ott"), ("F", "Pell")])]
        crowded["current_location"]["npcs"] = copy.deepcopy(crowd)
        crowded["locations"][0]["npcs"] = copy.deepcopy(crowd)
        inv = _involved(crowded, "I wave a stranger over.")
        self.assertEqual(len(inv["npcs"]), 4)
        self.assertEqual(inv["npcs"][-1]["status"], "new")
        self.assertEqual(sum(1 for n in inv["npcs"] if n["status"] == "known"), 3)

    def test_build_involved_new_name_rejects_clothing_and_duplicates(self):
        ctx = _context(cast_options={"names": ["Coat", "Mara", "Tamsin"], "jobs": []})
        inv = _involved(ctx, "I ask someone the way.")
        new = [n for n in inv["npcs"] if n["status"] == "new"]
        self.assertEqual([n["name"] for n in new], ["Tamsin"])
        self.assertEqual(new[0]["role_hint"], "local")
        from app.world import is_plausible_person_name

        ctx = _context(cast_options={"names": ["Coat", "Mara"], "jobs": []})
        em = scene_cast.entity_map_from_context(ctx)
        inv = _involved(ctx, "I ask someone the way.")
        name = [n for n in inv["npcs"] if n["status"] == "new"][0]["name"]
        self.assertTrue(is_plausible_person_name(name), name)
        self.assertNotIn(name.lower(), em["names_lower"])
        self.assertEqual(name, [n for n in _involved(ctx, "I ask someone the way.")["npcs"] if n["status"] == "new"][0]["name"])

    def test_build_involved_items_and_places(self):
        ctx = _context()
        ctx["inventory"] = [
            {"id": 1, "code": "I1", "name": "rusty knife"},
            {"id": 3, "code": "I3", "name": "travel-stained coat", "equipped_slot": "body"},
            {"id": 4, "code": "I4", "name": "rope"},
        ]
        ctx["current_location"]["parent_code"] = "L2"
        inv = _involved(ctx, "I coil the rope and head to the Market Square.")
        self.assertEqual([(i["slot"], i["ref"], i["kind"]) for i in inv["items"]], [("ITEM_1", "I3", "worn"), ("ITEM_2", "I4", "carried")])
        self.assertEqual([(p["slot"], p["code"], p["kind"]) for p in inv["places"]], [("PLACE_1", "L1", "here"), ("PLACE_2", "L2", "nearby")])
        inv = _involved(ctx, "I walk toward the Old Mill.")
        self.assertEqual(inv["places"][-1], {"slot": f"PLACE_{len(inv['places'])}", "code": None, "name": "Old Mill", "kind": "new"})

    def test_involved_legend_lines_and_normalize_roundtrip(self):
        ctx = _context(conversation_turn={"addressed": ["A"], "speech": True})
        inv = _involved(ctx, "I ask Mara and someone else about my coat.")
        self.assertEqual(
            inv["legend"],
            ["NPC_1=A:Mara (innkeeper)", "NPC_2=B:Dorn (guard captain)", "NPC_3=new:Tamsin (broker)", "ITEM_1=I3:travel-stained coat", "ITEM_2=I4:rope", "PLACE_1=L1:Second Shadow Inn", "PLACE_2=L2:Market Square"],
        )
        self.assertEqual(scene_cast.involved_legend(inv), inv["legend"])
        self.assertEqual(scene_cast.normalize_involved(json.loads(json.dumps(inv))), inv)
        self.assertIsNone(scene_cast.normalize_involved("garbage"))
        self.assertIsNone(scene_cast.normalize_involved({"npcs": [{"slot": "NPC_2"}]}))
        self.assertIsNone(scene_cast.normalize_involved({"npcs": "no"}))


class PlaceholderTests(unittest.TestCase):
    def test_normalize_placeholder_text_near_misses(self):
        text, fixes = scene_cast.normalize_placeholder_text("{npc_1} and {NPC1}, [NPC_1], {{NPC_1}}, {NPC 1|their}, {not_a_slot}, <item_2>")
        self.assertEqual(text, "{NPC_1} and {NPC_1}, {NPC_1}, {NPC_1}, {NPC_1|their}, {not_a_slot}, {ITEM_2}")
        self.assertEqual(len(fixes), 6)
        self.assertIn("{npc_1} -> {NPC_1}", fixes)
        self.assertEqual(scene_cast.normalize_placeholder_text("{NPC_1} stays"), ("{NPC_1} stays", []))

    def test_find_placeholders_positions_and_possessive(self):
        text = "{NPC_1}'s allies or {NPC_2}'s rebels; {ITEM_1|its} strap"
        found = scene_cast.find_placeholders(text)
        self.assertEqual([(p["slot"], p["possessive"], p["form"]) for p in found], [("NPC_1", True, ""), ("NPC_2", True, ""), ("ITEM_1", False, "its")])
        for p in found:
            self.assertEqual(text[p["start"]:p["end"]], p["raw"])
            self.assertEqual(p["where"], "narration")
        self.assertEqual(found[0]["index"], 1)
        self.assertEqual(found[2]["family"], "ITEM")

    def test_placeholders_in_turn_covers_every_text(self):
        turn = _turn("{NPC_1} nods.\n\n{PLACE_1} is quiet.", "SUMMARY {NPC_1} greets you.")
        turn["scene_plan"]["goal"] = "Meet {NPC_2}."
        wheres = [(p["slot"], p["where"]) for p in scene_cast.placeholders_in_turn(turn)]
        self.assertEqual(wheres, [("NPC_1", "narration"), ("PLACE_1", "narration"), ("NPC_1", "turn_summary"), ("NPC_2", "scene_plan"), ("NPC_1", "ops"), ("PLACE_1", "ops")])

    def test_slot_refs_in_ops(self):
        ops, _skipped = parse_ops_detailed('NPC_NEW NAME "{NPC_2}" ROLE broker\nCAST interacting {NPC_2}\nTALK {NPC_1} "the ford"\nREL {NPC_1} B "shares a drink"\nNPC_NOTE A "likes the ford"')
        refs = scene_cast.slot_refs_in_ops(ops)
        self.assertEqual([(r["op"], r["slot"], r["field"]) for r in refs], [("NPC_NEW", "NPC_2", "name"), ("CAST", "NPC_2", "code"), ("TALK", "NPC_1", "code"), ("REL", "NPC_1", "code")])
        self.assertEqual([r["line"] for r in refs], [1, 2, 3, 4])

    def test_is_slot_token_forms(self):
        for value in ("NPC_1", "{NPC_1}", "[[NPC_1]]", "npc_1", "{Npc_1|their}", '"{ITEM_2}"', "PLACE_3"):
            self.assertTrue(scene_cast.is_slot_token(value), value)
        for value in ("A", "L1", "Mara", "choose_direction", "{not_a_slot}", "", None, "NPC_"):
            self.assertFalse(scene_cast.is_slot_token(value), value)
        self.assertEqual(scene_cast.slot_of("[[npc_02]]"), "NPC_2")


class BindTests(unittest.TestCase):
    def setUp(self):
        self.ctx = _context(conversation_turn={"addressed": ["A"], "speech": True})
        self.em = scene_cast.entity_map_from_context(self.ctx)
        self.inv = _involved(self.ctx, "I ask Mara and someone else about my coat.")
        # NPC_1 Mara (A, she), NPC_2 Dorn (B, he), NPC_3 Tamsin (new, broker), ITEM_1 coat I3, ITEM_2 rope I4, PLACE_1 inn L1

    def test_bind_known_person_first_then_bare_and_pronouns(self):
        b = scene_cast.bind(_turn("{NPC_1} nods. {NPC_1|they} points {NPC_1|their} cup. {NPC_1} smiles at {NPC_2|them}; {NPC_2|he} shrugs."), self.inv, self.em)
        self.assertEqual(b["turn"]["narration"], "Mara [[A]] nods. She points her cup. Mara smiles at him; he shrugs.")
        self.assertEqual(b["turn"]["narration_segments"][0]["text"], b["turn"]["narration"])
        self.assertTrue(b["text_changed"])
        self.assertTrue(b["binding"]["slots"]["NPC_1"]["first_mention_done"])
        self.assertEqual(b["binding"]["unbound"], [])
        self.assertEqual(b["binding"]["replacements"][0], {"from": "{NPC_1}", "to": "Mara [[A]]", "where": "narration"})

    def test_bind_possessive_first_mention(self):
        b = scene_cast.bind(_turn("Choose: {NPC_1}'s allies or {NPC_1}'s rivals."), self.inv, self.em)
        self.assertEqual(b["turn"]["narration"], "Choose: Mara [[A]]'s allies or Mara's rivals.")
        self.assertEqual(scene_cast.render_slot(b["binding"]["slots"]["NPC_1"], first=True, possessive=True), "Mara [[A]]'s")
        self.assertEqual(scene_cast.render_slot(b["binding"]["slots"]["NPC_1"], form="first", first=False), "Mara")

    def test_bind_item_and_place_object_phrasing(self):
        b = scene_cast.bind(_turn("Rain beads on {ITEM_1}. You pull your {ITEM_1} tighter and step into {PLACE_1}. {PLACE_1} is warm; {ITEM_1|its} hem drips. {ITEM_1} steams."), self.inv, self.em)
        self.assertEqual(
            b["turn"]["narration"],
            "Rain beads on your travel-stained coat [[I3]]. You pull your travel-stained coat tighter and step into Second Shadow Inn [[L1]]. Second Shadow Inn is warm; its hem drips. Your travel-stained coat steams.",
        )

    def test_bind_new_face_name_only_and_npc_row_proposal(self):
        b = scene_cast.bind(_turn("{NPC_3} grins. {NPC_3|they} wave {NPC_3|their} hand. " + _LONG), self.inv, self.em)
        self.assertTrue(b["turn"]["narration"].startswith("Tamsin grins. They wave their hand."))
        self.assertEqual(len(b["binding"]["new_npcs"]), 1)
        row = b["binding"]["new_npcs"][0]
        for key in _NPC_ROW_KEYS:
            self.assertIn(key, row)
        self.assertEqual((row["code"], row["name"], row["role"], row["location"], row["presence"], row["_slot"]), (None, "Tamsin", "broker", "L1", "event_worthy", "NPC_3"))
        self.assertEqual(scene_cast.npc_rows_for_apply(scene_cast.attach_report(b["turn"], {"binding": b["binding"]})), [row])
        # An NPC_NEW row naming the slot is renamed in place, not duplicated.
        b2 = scene_cast.bind(_turn("{NPC_3} grins. " + _LONG, 'NPC_NEW NAME "{NPC_3}" ROLE broker LOC L1'), self.inv, self.em)
        self.assertEqual([(r["name"], r["_slot"], r["code"]) for r in b2["turn"]["npcs"]], [("Tamsin", "NPC_3", None)])
        self.assertEqual(b2["binding"]["new_npcs"], [])

    def test_bind_ops_cast_known_and_pending(self):
        b = scene_cast.bind(_turn("{NPC_1} and {NPC_3} talk. " + _LONG, 'CAST interacting {NPC_1}\nCAST present {NPC_3}\nTALK {NPC_3} "the ford"\nREL {NPC_1} {NPC_3} "old rivals"'), self.inv, self.em)
        self.assertEqual(b["turn"]["scene_cast"]["interacting"], ["A"])
        self.assertEqual(b["turn"]["scene_cast"]["present"], [])
        self.assertEqual(b["binding"]["pending_cast"], [{"slot": "NPC_3", "name": "Tamsin", "bucket": "present"}])
        self.assertEqual(b["turn"]["conversations"][0]["npc_code"], "Tamsin")
        self.assertEqual((b["turn"]["relationships"][0]["source_code"], b["turn"]["relationships"][0]["target_code"]), ("A", "Tamsin"))

    def test_bind_unbound_slot_left_and_listed(self):
        b = scene_cast.bind(_turn("{NPC_1} nods at {NPC_7}. {npc_7} waves."), self.inv, self.em)
        self.assertEqual(b["turn"]["narration"], "Mara [[A]] nods at {NPC_7}. {NPC_7} waves.")
        self.assertEqual(b["binding"]["unbound"], ["NPC_7"])
        self.assertEqual(b["binding"]["fixes"], ["{npc_7} -> {NPC_7}"])
        self.assertTrue(b["text_changed"])

    def test_bind_structured_keys_untouched(self):
        turn = _turn("{NPC_1} hands you bread. " + _LONG, 'GRANT "bread" QTY 1\nGOLD -2\nSUMMARY {NPC_1} sells bread.')
        b = scene_cast.bind(turn, self.inv, self.em)
        self.assertEqual(b["turn"]["inventory_changes"], turn["inventory_changes"])
        self.assertEqual(b["turn"]["player"], turn["player"])
        self.assertEqual(b["turn"]["turn_summary"], "Mara [[A]] sells bread.")
        self.assertEqual(turn["narration"][:8], "{NPC_1} ")  # the input turn is not mutated

    def test_bind_is_deterministic(self):
        turn = _turn("{NPC_1} nods; {NPC_3} laughs. " + _LONG)
        one = scene_cast.bind(turn, self.inv, self.em, seed=7)
        two = scene_cast.bind(turn, self.inv, self.em, seed=7)
        self.assertEqual(one, two)
        nameless = copy.deepcopy(self.inv)
        nameless["npcs"][2]["name"] = None
        a = scene_cast.bind(turn, nameless, self.em, seed=1)
        c = scene_cast.bind(turn, nameless, self.em, seed=2)
        self.assertNotEqual(a["binding"]["slots"]["NPC_3"]["ref"]["name"], c["binding"]["slots"]["NPC_3"]["ref"]["name"])
        self.assertEqual(a["binding"]["slots"]["NPC_1"], c["binding"]["slots"]["NPC_1"])
        self.assertEqual(a["turn"]["narration"].replace(a["binding"]["slots"]["NPC_3"]["ref"]["name"], "X"), c["turn"]["narration"].replace(c["binding"]["slots"]["NPC_3"]["ref"]["name"], "X"))

    def test_resolve_pending_cast_appends_codes(self):
        b = scene_cast.bind(_turn("{NPC_3} nods. " + _LONG, "CAST present {NPC_3}\nCAST interacting A"), self.inv, self.em)
        turn = scene_cast.attach_report(b["turn"], {"binding": b["binding"]})
        frozen = copy.deepcopy(turn)
        cast = scene_cast.resolve_pending_cast(turn, {"tamsin": "F", "Nobody": "Z"})
        self.assertEqual(cast, {"present": ["F"], "interacting": ["A"], "off": [], "keywords": []})
        self.assertEqual(turn, frozen)
        self.assertEqual(scene_cast.resolve_pending_cast(turn, {})["present"], [])

    def test_npc_rows_for_apply_reads_report(self):
        self.assertEqual(scene_cast.npc_rows_for_apply(_turn("Nothing.")), [])
        self.assertEqual(scene_cast.npc_rows_for_apply({"_dsl": {"scene_cast": {"binding": None}}}), [])


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.ctx = _context(conversation_turn={"addressed": ["A"], "speech": True})
        self.em = scene_cast.entity_map_from_context(self.ctx)
        self.inv = _involved(self.ctx, "I ask Mara and someone else about my coat.")

    def _bound(self, narration: str, ops: str = "") -> tuple[dict, dict]:
        b = scene_cast.bind(_turn(narration, ops), self.inv, self.em)
        return b["turn"], b["binding"]

    def test_verify_clean_turn_passes_all_gates(self):
        turn, binding = self._bound('{NPC_1} nods. "The ford is high," {NPC_1|they} says. {NPC_3} grins. ' + _LONG, 'NPC_NEW NAME "{NPC_3}" ROLE broker')
        v = scene_cast.verify(turn, self.inv, binding, self.em, player_input="I ask Mara.")
        self.assertTrue(v["ok"])
        self.assertEqual(v["policy_blockers"], [])
        self.assertEqual(v["warnings"], [])
        self.assertEqual([g["check"] for g in v["gates"]], [check for check, _sev in scene_cast.GATES])
        for gate in v["gates"]:
            _assert_shape(self, gate, _EVIDENCE_TYPES)
            self.assertTrue(gate["ok"], gate)
            self.assertEqual(gate["weight"], 0.0)
            self.assertIn(gate["severity"], ("block", "warn", "info"))
            self.assertLessEqual(len(gate["evidence"]), 240)
        self.assertEqual(v["counts"], {"placeholders": 0, "unbound": 0, "new_names": 1, "agent_items": 0, "agent_places": 0})

    def test_gate_placeholder_unbound_blocks(self):
        turn, binding = self._bound("{NPC_1} nods. " + _LONG)
        turn["scene_plan"]["goal"] = "Find {NPC_3} at the ford."
        v = scene_cast.verify(turn, self.inv, binding, self.em)
        self.assertFalse(v["ok"])
        self.assertEqual(v["policy_blockers"], ["placeholder_unbound"])
        gate = v["gates"][0]
        self.assertEqual(gate["evidence"], "scene_plan: Find {NPC_3} at the ford.")
        self.assertEqual(v["counts"]["placeholders"], 1)

    def test_gate_npc_slot_not_person(self):
        misfiled = copy.deepcopy(self.inv)
        misfiled["npcs"][1]["code"] = "I3"
        turn, binding = self._bound("Mara [[A]] nods. " + _LONG)
        v = scene_cast.verify(turn, misfiled, binding, self.em)
        self.assertIn("npc_slot_not_person", v["policy_blockers"])
        self.assertIn("NPC_2 bound to I3", [g for g in v["gates"] if g["check"] == "npc_slot_not_person"][0]["evidence"])
        generic = copy.deepcopy(self.inv)
        generic["npcs"][2]["name"] = "The Hooded Figure"
        v = scene_cast.verify(turn, generic, binding, self.em)
        self.assertIn("npc_slot_not_person", v["policy_blockers"])

    def test_gate_slot_name_is_clothing(self):
        clothing = copy.deepcopy(self.inv)
        clothing["npcs"][2]["name"] = "Travel Coat"
        turn, binding = self._bound("Mara [[A]] nods. " + _LONG)
        v = scene_cast.verify(turn, clothing, binding, self.em)
        self.assertIn("slot_name_is_clothing", v["policy_blockers"])
        self.assertEqual([g for g in v["gates"] if g["check"] == "slot_name_is_clothing"][0]["evidence"], "Travel Coat")
        turn["npcs"].append({"code": None, "name": "Window Bram", "role": "local"})
        v = scene_cast.verify(turn, self.inv, binding, self.em)
        self.assertIn("slot_name_is_clothing", v["policy_blockers"])

    def test_gate_item_as_agent_variants(self):
        names = ["travel-stained coat", "Rusty Knife"]
        for text in ("Choose: travel-stained coat's rebels or peace.", "[[I3]] says nothing.", "Rusty Knife's voice is low.", "Rusty Knife [[I1]] nods."):
            rows = scene_cast.gate_item_as_agent(text, names)
            self.assertTrue(rows, text)
            self.assertFalse(rows[0]["ok"])
            _assert_shape(self, rows[0], _EVIDENCE_TYPES)
            self.assertIn(rows[0]["evidence"].split()[0].lower(), text.lower())
        self.assertEqual(scene_cast.gate_item_as_agent("You pull your coat tighter and the rope holds.", names), [])
        turn, binding = self._bound("Mara [[A]] nods. The travel-stained coat's rebels wait outside. " + _LONG)
        v = scene_cast.verify(turn, self.inv, binding, self.em)
        self.assertEqual(v["policy_blockers"], ["item_as_agent"])
        self.assertEqual(v["counts"]["agent_items"], 1)

    def test_gate_place_as_agent(self):
        names = ["Second Shadow Inn", "Market Square"]
        for text in ("L1's allies gather.", "Second Shadow Inn [[L1]]'s men block the door.", "The inn watches you."):
            rows = scene_cast.gate_place_as_agent(text, names)
            self.assertTrue(rows, text)
            self.assertFalse(rows[0]["ok"])
        self.assertEqual(scene_cast.gate_place_as_agent("You enter the inn and sit by the square.", names), [])
        turn, binding = self._bound("Mara [[A]] nods. The inn watches you. " + _LONG)
        v = scene_cast.verify(turn, self.inv, binding, self.em)
        self.assertEqual(v["policy_blockers"], ["place_as_agent"])

    def test_gate_cast_overflow_with_figure_hints(self):
        turn = _turn("Mara [[A]] nods. A wiry woman leans on the bar. Bram waves. " + _LONG)
        turn["npcs"] = [{"code": None, "name": "Bram", "role": "carter"}, {"code": None, "name": "Ilse", "role": "scout"}]
        gate = scene_cast.gate_cast_overflow(turn, 1, ["Mara"])
        self.assertFalse(gate["ok"])
        self.assertTrue(gate["evidence"].startswith("3 new faces (limit 1)"), gate["evidence"])
        _assert_shape(self, gate, _EVIDENCE_TYPES)
        bound = _turn("Mara [[A]] nods. Tamsin, a wiry woman, leans on the bar. " + _LONG)
        bound["npcs"] = [{"code": None, "name": "Tamsin", "role": "broker", "_slot": "NPC_3"}]
        self.assertTrue(scene_cast.gate_cast_overflow(bound, 1, ["Mara", "Tamsin"])["ok"])
        v = scene_cast.verify(turn, self.inv, None, self.em)
        self.assertIn("cast_overflow", v["policy_blockers"])

    def test_gate_warnings_speaker_and_must_speak(self):
        turn, binding = self._bound('Mara [[A]] nods. "Go home," Wren [[E]] says from the doorway. ' + _LONG)
        v = scene_cast.verify(turn, self.inv, binding, self.em, player_input="I ask Mara.")
        self.assertTrue(v["ok"])
        checks = {g["check"]: g for g in v["gates"]}
        self.assertFalse(checks["speaker_outside_cast"]["ok"])
        self.assertTrue(checks["speaker_outside_cast"]["evidence"].startswith("E:"))
        self.assertEqual(checks["speaker_outside_cast"]["severity"], "warn")
        self.assertTrue(checks["must_speak_silent"]["ok"])  # Mara nods, an agent sentence
        turn, binding = self._bound("The fire crackles. Dorn [[B]] leans on the bar. " + _LONG)
        v = scene_cast.verify(turn, self.inv, binding, self.em)
        self.assertTrue(v["ok"])
        checks = {g["check"]: g for g in v["gates"]}
        self.assertFalse(checks["must_speak_silent"]["ok"])
        self.assertIn("NPC_1 Mara", checks["must_speak_silent"]["evidence"])
        self.assertEqual(len(v["warnings"]), 1)

    def test_gate_unlisted_and_slot_reused(self):
        turn, binding = self._bound("Mara [[A]] nods. " + _LONG)
        turn["npcs"] = [{"code": None, "name": "Ghostly Pete", "role": "local"}]
        checks = {g["check"]: g for g in scene_cast.verify(turn, self.inv, binding, self.em)["gates"]}
        self.assertFalse(checks["unlisted_new_npc"]["ok"])
        self.assertEqual(checks["unlisted_new_npc"]["evidence"], "Ghostly Pete")
        turn["npcs"] = [{"code": None, "name": "Tamsin", "role": "broker", "_slot": "NPC_3"}, {"code": None, "name": "Bram", "role": "carter", "_slot": "NPC_3"}]
        v = scene_cast.verify(turn, self.inv, binding, self.em)
        self.assertIn("slot_reused_for_two", v["policy_blockers"])


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.ctx = _context(conversation_turn={"addressed": ["A"], "speech": True})
        self.em = scene_cast.entity_map_from_context(self.ctx)
        self.inv = _involved(self.ctx, "I ask Mara and someone else about my coat.")

    def _bound(self, narration: str, ops: str = "") -> tuple[dict, dict]:
        b = scene_cast.bind(_turn(narration, ops), self.inv, self.em)
        return b["turn"], b["binding"]

    def _plan(self, turn: dict, binding: dict | None) -> tuple[dict, dict]:
        v = scene_cast.verify(turn, self.inv, binding, self.em)
        return v, scene_cast.propose_repairs(turn, v, binding, self.em, seed=3)

    def test_propose_repairs_none_when_clean(self):
        turn, binding = self._bound("Mara [[A]] nods. " + _LONG)
        _v, plan = self._plan(turn, binding)
        self.assertEqual(plan["mode"], "none")
        self.assertFalse(plan["needs_model_call"])
        self.assertEqual(plan["text"], "")

    def test_propose_repairs_refill_and_cut(self):
        turn, binding = self._bound("Mara [[A]] nods. " + _LONG)
        turn["narration"] = turn["narration"] + " Later {NPC_1} waves."
        turn["narration_segments"][-1]["text"] += " Later {NPC_1} waves."
        v, plan = self._plan(turn, binding)
        self.assertEqual(plan["mode"], "refill")
        self.assertEqual(plan["replacements"], [{"from": "{NPC_1}", "to": "Mara", "why": "refill_unbound"}])
        self.assertTrue(plan["text"].endswith("Later Mara waves."))
        self.assertEqual(plan["reasons"], ["placeholder_unbound"])
        turn, binding = self._bound("Mara [[A]] nods. " + _LONG)
        turn["narration"] = turn["narration"] + " Then {NPC_8} laughs at you."
        turn["narration_segments"][-1]["text"] += " Then {NPC_8} laughs at you."
        v, plan = self._plan(turn, binding)
        self.assertEqual(plan["mode"], "cut")
        self.assertEqual(plan["cut_sentences"], ["Then {NPC_8} laughs at you."])
        self.assertEqual(plan["reask_slots"], ["NPC_8"])
        fixed = scene_cast.apply_repairs(turn, plan)
        self.assertNotIn("{NPC_8}", fixed["narration"])
        self.assertTrue(fixed["narration"].endswith("wool."))
        self.assertEqual(fixed["player"], turn["player"])
        self.assertTrue(scene_cast.verify(fixed, self.inv, binding, self.em)["ok"])

    def test_propose_repairs_agent_head_rewrite(self):
        turn, binding = self._bound("Mara [[A]] nods. The coat's rebels wait outside. " + _LONG)
        _v, plan = self._plan(turn, binding)
        self.assertEqual(plan["mode"], "refill")
        self.assertEqual(plan["replacements"], [{"from": "The coat's rebels", "to": "the rebels", "why": "fix_agent_heads"}])
        self.assertIn("the rebels wait outside", scene_cast.apply_repairs(turn, plan)["narration"])
        turn, binding = self._bound("Mara [[A]] nods. [[I3]] says 'Go.' " + _LONG)
        _v, plan = self._plan(turn, binding)
        self.assertEqual(plan["mode"], "cut")
        self.assertEqual(plan["cut_sentences"], ["[[I3]] says 'Go.'"])
        turn, binding = self._bound("Mara [[A]] nods. Rope's voice hums and the rope's hand twitches. " + _LONG)
        _v, plan = self._plan(turn, binding)
        self.assertEqual(sorted(r["to"] for r in plan["replacements"]), ["its strap", "its voice"])

    def test_propose_repairs_rename_clothing_slot(self):
        clothing = copy.deepcopy(self.inv)
        clothing["npcs"][2]["name"] = "Travel Coat"
        b = scene_cast.bind(_turn("Mara [[A]] nods. {NPC_3} grins at you. " + _LONG, 'NPC_NEW NAME "{NPC_3}" ROLE broker'), clothing, self.em)
        turn, binding = b["turn"], b["binding"]
        self.assertEqual(turn["npcs"][0]["name"], "Travel Coat")
        v = scene_cast.verify(turn, clothing, binding, self.em)
        plan = scene_cast.propose_repairs(turn, v, binding, self.em, seed=3)
        self.assertEqual(plan["mode"], "refill")
        self.assertEqual(len(plan["renamed"]), 1)
        renamed = plan["renamed"][0]
        self.assertEqual((renamed["slot"], renamed["old"]), ("NPC_3", "Travel Coat"))
        from app.world import is_plausible_person_name

        self.assertTrue(is_plausible_person_name(renamed["new"]))
        fixed = scene_cast.apply_repairs(turn, plan)
        self.assertIn(renamed["new"] + " grins at you", fixed["narration"])
        self.assertEqual(fixed["npcs"][0]["name"], renamed["new"])
        self.assertEqual(plan, scene_cast.propose_repairs(turn, v, binding, self.em, seed=3))

    def test_propose_repairs_rewrite_when_too_many_cuts_or_overflow(self):
        turn, binding = self._bound("Mara [[A]] nods. " + _LONG)
        tail = " {NPC_7} laughs. {NPC_8} spits. {NPC_9} leaves."
        turn["narration"] += tail
        turn["narration_segments"][-1]["text"] += tail
        _v, plan = self._plan(turn, binding)
        self.assertEqual(plan["mode"], "rewrite")
        self.assertTrue(plan["needs_model_call"])
        self.assertEqual(plan["reask_slots"], ["NPC_7", "NPC_8", "NPC_9"])
        self.assertEqual(plan["text"], "")
        turn, binding = self._bound("Mara [[A]] nods. A wiry woman leans on the bar. A hooded man coughs. " + _LONG)
        _v, plan = self._plan(turn, binding)
        self.assertEqual(plan["mode"], "rewrite")
        self.assertEqual(plan["reasons"], ["cast_overflow"])
        short, binding = self._bound("Mara [[A]] nods. {NPC_8} laughs.")
        _v, plan = self._plan(short, binding)
        self.assertEqual(plan["mode"], "rewrite")  # under MIN_PROSE_AFTER_CUT

    def test_apply_repairs_segments_and_summary(self):
        turn = _turn("Mara [[A]] nods.\n\nThe fire pops. {NPC_8} waves.\n\n" + _LONG, "SUMMARY Mara and {NPC_8} wave.")
        plan = {"mode": "cut", "needs_model_call": False, "replacements": [{"from": "{NPC_8}", "to": "nobody", "why": "refill_unbound"}], "cut_sentences": ["The fire pops."], "reask_slots": [], "renamed": [], "npcs_dropped": [], "text": "", "reasons": ["placeholder_unbound"]}
        fixed = scene_cast.apply_repairs(turn, plan)
        self.assertEqual([seg["text"] for seg in fixed["narration_segments"]], ["Mara [[A]] nods.", "nobody waves.", _LONG])
        self.assertEqual(fixed["narration"], "Mara [[A]] nods.\n\nnobody waves.\n\n" + _LONG)
        self.assertEqual(fixed["turn_summary"], "Mara and nobody wave.")
        self.assertEqual(scene_cast.report_of(fixed)["repairs"], plan)
        self.assertEqual(turn["narration_segments"][1]["text"], "The fire pops. {NPC_8} waves.")
        plan["cut_sentences"] = ["The fire pops.", "nobody waves."]
        fixed = scene_cast.apply_repairs(turn, plan)
        self.assertEqual(len(fixed["narration_segments"]), 2)
        self.assertEqual(fixed["narration"], "Mara [[A]] nods.\n\n" + _LONG)


class ReportTests(unittest.TestCase):
    def test_attach_report_only_under_dsl(self):
        from app import llm

        turn = _turn("Mara [[A]] nods. " + _LONG)
        keys = set(turn)
        scene_cast.attach_report(turn, {"gates": [scene_cast._evidence("placeholder_unbound", True, "", "block")]})
        scene_cast.attach_report(turn, {"binding": {"slots": {}, "unbound": [], "new_npcs": [], "pending_cast": [], "replacements": [], "fixes": [], "seed": 0}})
        self.assertEqual(set(turn), keys)
        report = scene_cast.report_of(turn)
        self.assertEqual(set(report), {"involved", "binding", "gates", "repairs", "version"})
        self.assertEqual(report["version"], 1)
        self.assertEqual(len(report["gates"]), 1)
        self.assertEqual(report["binding"]["seed"], 0)
        cleaned = llm._clean_turn_for_handoff(turn, "dsl_to_verify")
        self.assertEqual(scene_cast.report_of(cleaned)["binding"]["seed"], 0)
        self.assertNotIn("scene_cast_report", cleaned)
        self.assertIsNone(scene_cast.report_of({}))
        self.assertIsNone(scene_cast.report_of({"_dsl": {}}))


class EndToEndTests(unittest.TestCase):
    def test_end_to_end_from_dsl_text(self):
        ctx = _context(conversation_turn={"addressed": ["A"], "speech": True})
        em = scene_cast.entity_map_from_context(ctx)
        out = scene_cast.build_involved(ctx, "I ask Mara and someone else about my coat.", turn=3)
        inv = out["involved"]
        self.assertEqual([n["slot"] for n in inv["npcs"]], ["NPC_1", "NPC_2", "NPC_3"])
        reply = (
            "===NAR===\n"
            "Rain drips from {ITEM_1} as you step into {PLACE_1}. \"Choose your side—{NPC_1}'s allies or {NPC_3}'s rebels,\" "
            "{NPC_3} says from the corner. {NPC_1|they} frowns, sets down {NPC_1|their} cup and shakes {NPC_1|their} head. "
            + _LONG
            + "\n===OPS===\n"
            'NPC_NEW NAME "{NPC_3}" ROLE broker LOC L1\n'
            "CAST interacting {NPC_3}\n"
            "CAST present {NPC_1}\n"
            'TALK {NPC_1} "the ford"\n'
            "SUMMARY {NPC_1} and {NPC_3} argue over the ford.\n"
        )
        turn = parse_dsl_turn(reply, "I ask Mara and someone else about my coat.")
        b = scene_cast.bind(turn, inv, em, seed=1)
        self.assertIn("Mara [[A]]'s allies or Tamsin's rebels", b["turn"]["narration"])
        self.assertTrue(b["turn"]["narration"].startswith("Rain drips from your travel-stained coat [[I3]] as you step into Second Shadow Inn [[L1]]."))
        self.assertIn("She frowns, sets down her cup and shakes her head.", b["turn"]["narration"])
        self.assertEqual(b["turn"]["turn_summary"], "Mara [[A]] and Tamsin argue over the ford.")
        self.assertEqual(b["turn"]["scene_cast"]["present"], ["A"])
        self.assertEqual(b["binding"]["pending_cast"], [{"slot": "NPC_3", "name": "Tamsin", "bucket": "interacting"}])
        self.assertEqual(b["turn"]["npcs"][0]["name"], "Tamsin")
        self.assertEqual(b["turn"]["conversations"][0]["npc_code"], "A")
        scene_cast.attach_report(b["turn"], {"involved": inv, "binding": b["binding"]})
        v = scene_cast.verify(b["turn"], inv, b["binding"], em, player_input="I ask Mara and someone else about my coat.")
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["warnings"], [])
        plan = scene_cast.propose_repairs(b["turn"], v, b["binding"], em, seed=1)
        self.assertEqual(plan["mode"], "none")
        self.assertEqual(scene_cast.resolve_pending_cast(b["turn"], {"Tamsin": "F"})["interacting"], ["F"])


if __name__ == "__main__":
    unittest.main()
