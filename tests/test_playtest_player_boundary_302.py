"""
Playtest #30 / #42 / #52 under the writer-off default (AI_RPG_NARRATION_PIPELINE=0).

Every fixture below is live text from the blind A/B (arm B, writer off) or the
batch 4 gate, copied verbatim. The draft's own prose is what ships now, so the
player boundary, grant grounding and the depth floor are judged on it.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn_302_"))
os.environ.update(isolated_data_env(str(_TMP)))
for _key, _name in (
    ("AI_RPG_IDEA_BANK", "idea_bank.json"),
    ("AI_RPG_LAUNCHER_PREFS", "launcher_prefs.json"),
    ("AI_RPG_SKILL_LIBRARY", "skill_library.json"),
):
    os.environ.setdefault(_key, str(_TMP / _name))
os.environ.setdefault("AI_RPG_PACK_DIR", str(_TMP / "packs"))

from app import llm, world  # noqa: E402
from app.prompts import PROSE_VOICE  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT, build_dsl_user_prompt, narration_length_target, narration_depth_floor  # noqa: E402

WRITER_OFF = {
    "AI_RPG_NARRATION_PIPELINE": "0",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}

# --- live fixtures -------------------------------------------------------------

B_G1_T2_INPUT = "Lin Zhuo, come with me. Let's go after that cloaked figure before they slip off into the wastes."
B_G1_T2 = (
    "You step forward, and Lin Zhuo [[A]] follows, her gaze fixed on the cloaked figure that vanished into the Whispering Wastes. "
    "The wind carries the scent of dust and something older, something that makes the hairs on your neck rise. You push through "
    "the thinning veil of the threshold, where the land stretches into a vast, cracked expanse of pale sand. The sky is a pale blue, "
    "and the sun hangs high, but the heat is oppressive, as if the land itself is holding its breath.\n\n"
    "Lin Zhuo [[A]] moves with purpose, her boots crunching over the brittle ground. She does not speak, and you do not question her. "
    "You follow, your breath shallow, your senses on edge. The sand shifts underfoot, and the wind howls through the dunes, carrying "
    "with it whispers that are not quite words. You feel the weight of unseen eyes, and for a moment, you wonder if the cloaked figure "
    "is even real—or if you are being watched by something else entirely.\n\n"
    "Then, the ground gives way beneath you. A deep fissure opens, and you barely manage to leap back as the sand collapses into a dark "
    "chasm. Lin Zhuo [[A]]’s hand catches yours, and you feel the tension in her grip. She nods toward the edge of the fissure, where "
    "the sand has settled into a thin layer, and you both step closer, peering into the darkness below. The light from above barely "
    "reaches the bottom, and the silence is absolute, broken only by the distant echo of something moving.\n\n"
    "You exchange a glance with Lin Zhuo [[A]], and she gives a small, grim smile. “It’s not safe to go further,” she says, "
    "her voice steady. “But if we stay here, we might never catch up.”\n\n"
    "You nod, your mind already racing through the possibilities. The cloaked figure is gone, but something is waiting for you in the "
    "depths of the wastes. And you have no choice but to follow."
)

B_G2_T4_INPUT = "I follow the refugees east along the path toward the town, with Kendra Sallow beside me."
B_G2_T4 = (
    "The path ahead is rough, the dust rising in thin plumes from beneath your boots. The sun beats down, and the weight of the day "
    "presses on your shoulders. The refugee group moves with a mix of desperation and resolve, their faces lined with worry and "
    "exhaustion. Kendra Sallow [[A]] walks beside you, her rifle slung across her back, her gaze scanning the horizon for threats. "
    "She speaks little, but her presence is a steady anchor in the chaos.\n\n"
    "You press on, following the group eastward, the trail narrowing as it snakes through the hills. The terrain is rocky, and the "
    "sun beats down mercilessly. You can feel the heat rising from the ground, and the sweat that beads on your brow. The path is "
    "littered with abandoned belongings—clothes, tools, and even a few broken crates. The weight of the journey is heavy, but you "
    "push forward, driven by the need to reach the promised safety of the next settlement.\n\n"
    "As the group moves, you catch glimpses of the people they carry with them. A young mother clutches her child tightly, her face "
    "pale with fear. An old man limps along, his clothes tattered and his hands shaking. The group is a mix of ages and backgrounds, "
    "but all share the same look of determination. You can't help but feel a pang of sympathy for them, but you know that the journey "
    "is only beginning.\n\n"
    "Kendra stops suddenly, her hand on her rifle. She signals for silence, and the group slows to a halt. You strain your ears, "
    "listening for any sign of danger. The silence is oppressive, broken only by the occasional creak of a branch or the rustle of "
    "leaves. You wait, your heart pounding, as the tension builds.\n\n"
    "Just as you're about to speak, a sharp whistle cuts through the silence. Kendra's rifle is up in an instant, her finger on the "
    "trigger. The group freezes, and you hold your breathe, waiting for the shot."
)

B_G2_T5_INPUT = "I go into the first shop I can find in town to see what they sell."
B_G2_T5 = (
    "You step into the first shop you can find in the small settlement, a modest storefront with a sign reading \"Trask and "
    "Daughters.\" Inside, the space is dimly lit by a single oil lamp, and the smell of aged parchment and ink fills the room. Shelves "
    "line the walls, stacked with jars of dried herbs, bolts of rough-spun fabric, and bundles of dried moss. A counter runs along one "
    "side, cluttered with tools and a small ledger. Behind the counter stands a woman in her fifties, her face lined with years of "
    "weather and work, her hands calloused from years of handling goods.\n\n"
    "\"You're looking for supplies, then?\" she asks, her tone dry but not unkind. \"We’ve got what’s needed for the road, but "
    "the prices are high here. You’re not from around these parts, are you?\"\n\n"
    "You nod, your gaze sweeping the room for anything that might be useful. The shelves are packed with goods, but nothing seems "
    "particularly valuable. A few dried fruits and a small bundle of dried fish are on display, along with a few bolts of cloth and a "
    "handful of tools. A map of the region is tacked to the wall, its edges frayed and its ink faded. The woman watches you closely, "
    "as if expecting you to ask for more than what’s on display."
)

R2_G2_T5_INPUT = (
    "I give up on the figure for now, walk back to the outskirts and go inside the first trading post to see what they sell."
)
R2_G2_T5 = (
    "You give up on the figure, turning back toward the outskirts. The path ahead is clear, the morning light cutting through the "
    "mist, and the weight of the charred ledger [[I4]] feels less oppressive with each step. Humphrey Fowler [[A]] watches you go, his "
    "expression unreadable, but he doesn't stop you.\n\n"
    "The first trading post [[L4]] comes into view, its wooden walls weathered but sturdy, a sign of the hard-won trade that thrives "
    "in this place. You step inside, the smell of oil and dried herbs filling your nostrils. The shopkeeper, a grizzled man with a "
    "sharp eye, greets you with a nod, his gaze lingering on the charred ledger [[I4]] slung over your shoulder.\n\n"
    "He gestures toward the goods laid out on the counter—barrels of coal, bolts of cloth, and a few oddities that seem to have "
    "come from far-off places. You browse, your fingers brushing over the rough textures, your mind weighing the value of each item. "
    "The shop is quiet, save for the occasional clink of a coin hitting the counter.\n\n"
    "You decide to buy a few essentials, knowing that the journey ahead will demand more than just your strength. The shopkeeper, "
    "Humphrey Fowler [[A]], leans forward, his brow furrowed as he studies the charred ledger [[I4]] in your satchel. \"That's not just "
    "any ledger,\" he says, his voice low. \"That's a record of debts unpaid. You're carrying a burden that won't stay buried.\""
)

R1_G2_T3_INPUT = "I crouch and examine the ground where he stood for footprints or anything he dropped."
R1_G2_T3 = (
    "You crouch and examine the ground where he stood, brushing away loose dirt with careful fingers. The soil is dry and packed, but "
    "there's no sign of footprints—no deep indentations, no scattered gravel. You sweep your hand over the surface, feeling for "
    "anything he might have dropped. A small, jagged shard of metal glints in the morning light. You pick it up, turning it over in "
    "your palm. It's too sharp to be a tool, too heavy for a trinket.\n\n"
    "It looks like a shard of a broken compass, but the markings are unfamiliar. You pocket it, keeping it close. Nesta Grisham [[A]] "
    "watches you from a few paces away, arms crossed, her expression unreadable. She hasn't said a word since you arrived, and the "
    "silence between you is thick."
)

R2_G1_T5_INPUT = "I step back from the foundry gate and go into the nearest shop on the street to see what they sell."
R2_G1_T5 = (
    "You step back from the foundry gate and cross the street, the soles of your boots crunching on cobbles as you approach the "
    "nearest shop. Inside, the shop is dimly lit, with shelves lined with bottles and jars filled with strange substances.\n\n"
    "You pick up a vial of deep blue liquid, its label faded and barely legible. As you hold it up to the light, a flicker of "
    "interest crosses the shopkeeper's face. “Interesting choice,” he says, his tone slightly more curious now. “That's a "
    "rare one. It's used for healing wounds, but it's not common.” You set the vial down and glance at the books, their spines "
    "cracked and inked with alchemical formulas."
)

B_G2_T0_DRAFT = (
    "The morning sun casts long shadows across the Mudflat Shrine Path, where the air smells of damp earth and salt. A narrow road "
    "winds through the mud, leading to a shrine half-buried in the ground, its stone pillars worn smooth by time. You stand at the edge "
    "of the path, your boots sinking slightly into the soft ground. To your left, a small group of refugees huddle near a fire, their "
    "faces etched with exhaustion. To your right, a lone figure in a flat cap and patched blouse stands at the base of the shrine, "
    "staring into the distance. The path ahead is clear, but the ground is uneven, and the wind carries the distant sound of a train "
    "whistle.\n\n"
    "You have two choices: approach the refugees, or follow the lone figure toward the shrine. Each path leads to something different "
    "— and both are fraught with risk."
)
B_G2_T0_RETRY = (
    "The morning sun casts long shadows across the Mudflat Shrine Path [[L1]], where the air smells of damp earth and salt. The narrow "
    "road winds through the mud like a cracked vein, leading to a shrine half-buried in the ground.\n\n"
    "To your left, a small group of refugees huddle near a fire, their faces etched with exhaustion. One woman, her hair matted with "
    "grime, stirs a pot of murky stew, its scent mingling with the stench of sweat and despair. A child, no more than six, clutches a "
    "frayed blanket to their chest, eyes wide and wary. Their leader, a man with a scar running from his temple to his jaw, watches "
    "you with a mix of suspicion and hope, as if you might be the answer to a prayer or the herald of a curse.\n\n"
    "To your right, a lone figure in a flat cap and patched blouse stands at the base of the shrine, staring into the distance. The "
    "path ahead is clear, but the ground is uneven, and the wind carries the distant sound of the train whistle, a reminder that time "
    "is not on your side.\n\n"
    "You have two choices: approach the refugees, or follow the lone figure toward the shrine. Each path leads to something "
    "different—and both are fraught with risk."
)
B_G2_T1_DRAFT = (
    "Kendra Sallow stops mid-step, her hand tightening on the reins of the stagecoach. The refugees, a cluster of ragged figures with "
    "hollow eyes, shuffle past you like shadows under a flickering lantern. She turns to you, her face a mask of weary determination.\n\n"
    "\"Town’s got a new magistrate,\" she says, her voice low and edged with something like warning. \"He’s got a reputation "
    "for clearing out the old debts—yours included.\" Her gaze flicks to the refugees, who are now moving faster, their pace "
    "frantic. \"They’re not just heading to town. They’re running from something. Something the magistrate’s men are after.\"\n\n"
    "She leans closer, her breath a whisper against your ear. \"If you’re looking for answers, you’ll find them in the ruins. "
    "But be careful—what you find there might not be worth the risk.\""
)
B_G2_T1_RETRY_TAIL = (
    " Her voice drops lower, as if the very air might carry it to the ears of those chasing them. \"The magistrate’s men don’t "
    "ask questions. They don’t give second chances. And if you’re not careful, you’ll end up like the ones who came before you.\""
)


# Distinct sentences: _normalize_turn folds repeated ones, so a repeated line
# would not measure 700 characters.
_DRAFT_700 = (
    "The lamp hisses over the counter while the keeper counts her coins into a tin. "
    "Rain ticks against the shutters, and the street outside has emptied for the night. "
    "A shelf of jars runs the length of the back wall, each one labelled in a cramped hand. "
    "Somewhere upstairs a child is practising scales on a cracked flute, badly and with spirit. "
    "The floorboards by the door are worn pale where a thousand boots have stopped to stamp. "
    "A cat sleeps on a sack of lentils, one ear twitching whenever the keeper's coins clink. "
    "Behind the counter hangs a slate of prices, half of them crossed out and written again. "
    "The air smells of lamp oil, wet wool and the sharp green of cut herbs drying on a string."
)


def _turn(narration: str) -> dict:
    return {
        "narration": narration,
        "narration_segments": [{"label": "paragraph", "text": p} for p in narration.split("\n\n") if p.strip()],
        "self_check": {"corrections_made": []},
    }


def _inv_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE inventory (id INTEGER PRIMARY KEY, name TEXT, quantity REAL, dimensional_space INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE journal (id INTEGER PRIMARY KEY, turn INTEGER, kind TEXT, content TEXT)")
    conn.execute("CREATE TABLE pacing (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def _tokens(name: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9']{4,}", name.lower())


class WriterOffEnv(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, WRITER_OFF)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("AI_RPG_MIN_NARRATION_CHARS", None)


# --- 30-ask --------------------------------------------------------------------


class PlayerBoundaryAsk(WriterOffEnv):
    def test_dsl_ask_gives_the_player_their_actions_thoughts_and_decisions(self):
        for needle in ("thoughts", "decisions", "further actions"):
            self.assertIn(needle, DSL_SYSTEM_PROMPT)
        self.assertIn("player_line is the player's own input", DSL_SYSTEM_PROMPT)
        packet = json.loads(build_dsl_user_prompt({}, B_G1_T2_INPUT))
        joined = " ".join(packet.get("instructions") or []) if isinstance(packet.get("instructions"), list) else json.dumps(packet)
        self.assertIn("thoughts", joined)
        self.assertIn("decisions", joined)

    def test_prose_voice_has_no_journey_example_and_states_the_rule(self):
        self.assertNotIn("narrate the journey", PROSE_VOICE)
        self.assertNotIn('"I walk east"', PROSE_VOICE)
        self.assertIn("thoughts", PROSE_VOICE)
        self.assertIn('all that "you" say and do this turn', PROSE_VOICE)

    def test_grant_ask_names_givers_and_the_players_own_taking(self):
        flat = " ".join(DSL_SYSTEM_PROMPT.split())
        self.assertNotIn("===NAR=== puts in the player's hands", flat)
        self.assertIn("player_line itself takes, buys or loots", flat)

    def test_opening_request_does_not_ask_for_a_first_choice(self):
        self.assertNotIn("first choice", world.OPENING_SCENE_INPUT)

    def test_length_ask_scales_with_the_action_and_the_floor(self):
        short = narration_length_target("I crouch and examine the symbols etched into the shrine wall.")
        self.assertEqual(short, "about 700-950 characters")
        self.assertEqual(narration_length_target(B_G2_T4_INPUT), "about 900-1400 characters")
        self.assertEqual(narration_length_target("__opening_scene_request__"), "about 1000-1800 characters")
        with mock.patch.dict(os.environ, {"AI_RPG_MIN_NARRATION_CHARS": "800"}):
            self.assertEqual(narration_length_target("I open the door."), "about 900-1150 characters")

    def test_writer_on_keeps_the_old_length_ask(self):
        with mock.patch.dict(os.environ, {"AI_RPG_NARRATION_PIPELINE": "1"}):
            self.assertEqual(narration_length_target("I open the door."), "about 1000-1200 characters")


# --- 30-engine-pass --------------------------------------------------------------


class InventedPlayerActsDrop(WriterOffEnv):
    def _run(self, narration: str, player_input: str) -> dict:
        return llm._drop_invented_player_acts(_turn(narration), player_input)

    def test_b_g1_t2(self):
        out = self._run(B_G1_T2, B_G1_T2_INPUT)["narration"]
        for gone in ("You nod", "your mind already racing", "no choice but to follow", "you wonder"):
            self.assertNotIn(gone, out)
        # The player said "go after"; following is their own action.
        self.assertIn("You follow, your breath shallow", out)
        self.assertIn("You feel the weight of unseen eyes.", out)
        self.assertIn("“It’s not safe to go further,” she says", out)
        self.assertIn("The cloaked figure is gone", out)

    def test_b_g2_t4(self):
        out = self._run(B_G2_T4, B_G2_T4_INPUT)["narration"]
        self.assertNotIn("pang of sympathy", out)
        self.assertNotIn("you know that the journey", out)
        self.assertIn("Just as you're about to speak", out)
        self.assertIn("You press on, following the group eastward", out)
        self.assertIn("You strain your ears", out)

    def test_b_g2_t5(self):
        out = self._run(B_G2_T5, B_G2_T5_INPUT)
        self.assertNotIn("You nod", out["narration"])
        self.assertIn("You’re not from around these parts, are you?", out["narration"])
        self.assertIn("The shelves are packed with goods", out["narration"])
        self.assertTrue(out["_invented_player_acts"])
        self.assertTrue(any("player" in c for c in out["self_check"]["corrections_made"]))
        self.assertEqual("\n\n".join(s["text"] for s in out["narration_segments"]), out["narration"])

    def test_r2_g2_t5(self):
        out = self._run(R2_G2_T5, R2_G2_T5_INPUT)["narration"]
        self.assertNotIn("You decide to buy", out)
        self.assertIn("You browse", out)
        self.assertIn("That's not just any ledger", out)

    def test_r1_g2_t3_invented_pickup_and_pocket(self):
        out = self._run(R1_G2_T3, R1_G2_T3_INPUT)["narration"]
        self.assertNotIn("You pick it up", out)
        self.assertNotIn("You pocket it", out)
        self.assertIn("A small, jagged shard of metal glints", out)

    def test_negatives_are_left_alone(self):
        cases = [
            ("I look around the market.", "You see a cart of turnips and hear a dog bark. You notice a woman counting coins. She hands you a leaflet about the fair, smiling. The stalls run on for a long way, crowded and loud, and the air smells of bread and horse."),
            ("I nod and smile at the guard.", "You nod and smile at the guard. He grunts and waves you through the gate, back to his dice game with the other watchman, who has not looked up once since you came close enough to see his face."),
            ("Mara, what happened here?", "You ask Mara what happened, and she looks at the broken window for a long moment before she shrugs and points at the street, where the glass still lies glittering in the gutter beside an overturned barrow."),
            ("I pick up the brass key from the table.", "You pick up the brass key, cold and heavier than it looks. You pocket it. The room is quiet; somewhere above, a floorboard creaks under a slow weight and then goes still."),
            ("I follow the figure through the archway.", "You glance back, and for a moment, you think you see a flicker of movement in the distance, a shadow that does not belong. The archway behind you is empty, and the wind has dropped to nothing over the pale sand of the wastes."),
            ("I wait by the door.", "“You nod when I speak,” she says, “and you decide nothing.” The fire pops. The door stays shut, and the wind outside has found a gap in the shutters that whistles every time it gusts across the yard."),
        ]
        for player_input, narration in cases:
            with self.subTest(player_input=player_input):
                out = self._run(narration, player_input)
                self.assertEqual(out["narration"], narration)

    def test_live_nod_then_the_keepers_answer_keeps_the_answer(self):
        # Live f3042 g1 t5: dropping the whole sentence lost the shop's goods.
        text = (
            "You head back and slip into the nearest shop, where the scent of tanned hides and dried herbs lingers in the dry "
            "morning breeze. The shopkeeper, a wiry man with a face like weathered leather, looks up from his work. "
            "You nod, and he gestures toward the shelves behind him, where bundles of dried roots, vials of shimmering ink, "
            "and bolts of coarse fabric are stacked haphazardly."
        )
        out = self._run(text, "I head back and go into the nearest shop to see what they sell.")["narration"]
        self.assertNotIn("You nod", out)
        self.assertIn("He gestures toward the shelves behind him, where bundles of dried roots", out)

    def test_floor_keeps_a_tiny_scene(self):
        text = "You nod. The door is shut."
        self.assertEqual(self._run(text, "I wait.")["narration"], text)

    def test_quality_chain_runs_the_drop_before_returning(self):
        passthrough = lambda t, *a, **k: t  # noqa: E731
        with mock.patch.object(llm, "_ensure_narration_depth", side_effect=passthrough), \
                mock.patch.object(llm, "_ensure_narration_voice", side_effect=passthrough), \
                mock.patch.object(llm, "_ensure_answer_act", side_effect=passthrough), \
                mock.patch.object(llm, "_ensure_recall_specifics", side_effect=passthrough):
            trace: list = []
            out = llm._ensure_narration_quality(_turn(B_G2_T5), {}, B_G2_T5_INPUT, "sys", 30, [], "test", trace)
        self.assertNotIn("You nod", out["narration"])
        self.assertTrue(any(e.get("event") == "invented_player_acts_dropped" for e in trace))


# --- 42 grant grounding / put down ----------------------------------------------------


class GrantGrounding(WriterOffEnv):
    def _kept(self, name: str, narration: str, player_input: str) -> bool:
        conn = _inv_conn()
        kept = world._filter_inventory_changes(
            conn, [{"name": name, "quantity_delta": 1}], narration=narration, player_input=player_input,
            input_kind="player", draft_narration=narration,
        )
        return bool(kept)

    def test_live_compass_shard_from_an_examine(self):
        self.assertFalse(self._kept("shard of broken compass", R1_G2_T3, R1_G2_T3_INPUT))

    def test_live_vial_from_a_browse(self):
        self.assertFalse(self._kept("vial of deep blue liquid", R2_G1_T5, R2_G1_T5_INPUT))

    def test_synthetic_look_only_pickup(self):
        prose = "You crouch and examine the ground. A small brass key glints in the dirt. You pick it up, turning it over in your palm. You pocket it, keeping it close."
        self.assertFalse(self._kept("brass key", prose, "I examine the ground for tracks."))

    def test_the_player_taking_it_is_granted(self):
        prose = "You pick up the brass key and turn it in the light. You pocket it."
        self.assertTrue(self._kept("brass key", prose, "I pick up the brass key."))
        self.assertTrue(self._kept("brass key", "You buy a brass key from the stall and pocket it.", "I buy the brass key."))

    def test_a_world_handover_is_granted_without_intent(self):
        prose = "The keeper reaches under the counter and hands you a brass key. “For the back room,” she says."
        self.assertTrue(self._kept("brass key", prose, "I ask the keeper where I can sleep."))

    def test_a_shop_i_can_find_is_not_taking(self):
        # Live f3042 g2 t5: herbs on a shelf, granted because the input said "find".
        prose = (
            "You step into the first shop you can find in town. The walls are lined with bolts of fabric, tools, and "
            "dried herbs. A man with a grizzled beard leans against a counter. \u201cLooking for anything in particular?\u201d he asks."
        )
        self.assertFalse(self._kept("dried herbs", prose, "I go into the first shop I can find in town to see what they sell."))

    def test_rejection_is_journaled(self):
        conn = _inv_conn()
        world._filter_inventory_changes(
            conn, [{"name": "brass key", "quantity_delta": 1}],
            narration="A brass key lies in the dirt. You pick it up and pocket it.",
            player_input="I look around.", input_kind="player",
        )
        rows = [r[0] for r in conn.execute("SELECT content FROM journal WHERE kind = 'inventory_reject'")]
        self.assertTrue(rows and "brass key" in rows[0], rows)


class PutDownIsALoss(unittest.TestCase):
    def test_live_vial_sentence(self):
        text = "You pick up a vial of deep blue liquid. You set the vial down and glance at the books."
        self.assertEqual(world._prose_item_outcome(text, "vial of deep blue liquid", _tokens("vial of deep blue liquid")), "loss")

    def test_other_put_down_forms(self):
        for closing in ("You put it down again.", "You lay it back on the shelf.", "You place it on the counter.",
                        "You set it aside.", "You put the brass key back."):
            with self.subTest(closing=closing):
                text = "You pick up a brass key. " + closing
                self.assertEqual(world._prose_item_outcome(text, "brass key", ["brass"]), "loss")

    def test_an_npc_setting_it_down_is_not_a_player_loss(self):
        text = "She sets the vial down in front of you and takes your coin."
        self.assertNotEqual(world._prose_item_outcome(text, "vial", ["vial"]), "loss")
        conn = _inv_conn()
        kept = world._filter_inventory_changes(conn, [{"name": "vial", "quantity_delta": 1}], narration=text,
                                               player_input="I buy the vial.", input_kind="player")
        self.assertTrue(kept)


# --- 52 floor ------------------------------------------------------------------------


class DepthFloor(WriterOffEnv):
    def test_default_and_env_and_clamp(self):
        self.assertEqual(narration_depth_floor(), 600)
        for raw, want in (("800", 800), ("50", 300), ("99999", 1500), ("junk", 600), ("", 600)):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {"AI_RPG_MIN_NARRATION_CHARS": raw}):
                self.assertEqual(narration_depth_floor(), want)

    def test_a_700_char_draft_is_not_retried_by_default(self):
        draft = _DRAFT_700
        calls = []

        def fake_retry(*a, **k):
            calls.append(1)
            raise llm.LlmError("should not run")

        with mock.patch.object(llm, "_retry_narration_prose", side_effect=fake_retry), \
                mock.patch.object(llm, "_retry_short_narration", side_effect=fake_retry):
            out = llm._ensure_narration_depth({"narration": draft}, {}, "I wait.", "sys", 30, [], "p", [])
        self.assertEqual(calls, [])
        self.assertEqual(out["narration"].strip(), draft.strip())

    def test_env_floor_is_used_by_the_depth_retry(self):
        draft = _DRAFT_700
        calls = []

        def fake_retry(*a, **k):
            calls.append(1)
            raise llm.LlmError("no")

        with mock.patch.dict(os.environ, {"AI_RPG_MIN_NARRATION_CHARS": "900"}), \
                mock.patch.object(llm, "_retry_narration_prose", side_effect=fake_retry), \
                mock.patch.object(llm, "_retry_short_narration", side_effect=fake_retry):
            llm._ensure_narration_depth({"narration": draft}, {}, "I wait.", "sys", 30, [], "p", [])
        self.assertTrue(calls)

    def test_writer_on_keeps_the_1000_floor(self):
        draft = _DRAFT_700
        calls = []

        def fake_retry(*a, **k):
            calls.append(1)
            raise llm.LlmError("no")

        with mock.patch.dict(os.environ, {"AI_RPG_NARRATION_PIPELINE": "1"}), \
                mock.patch.object(llm, "_retry_narration_prose", side_effect=fake_retry), \
                mock.patch.object(llm, "_retry_short_narration", side_effect=fake_retry):
            llm._ensure_narration_depth({"narration": draft}, {}, "I wait.", "sys", 30, [], "p", [])
        self.assertTrue(calls, "writer on: 700 < 1000 still retries")
        self.assertEqual(llm.MIN_TURN_NARRATION_CHARS, 1000)

    def test_menu_trim_floor_is_its_own(self):
        import inspect

        for fn in (llm._trim_menu_ending, llm._trim_option_list):
            self.assertEqual(inspect.signature(fn).parameters["floor"].default, llm.MENU_TRIM_FLOOR_CHARS)
        with mock.patch.dict(os.environ, {"AI_RPG_MIN_NARRATION_CHARS": "1500"}):
            out, removed = llm._trim_menu_ending(B_G2_T0_DRAFT)
        self.assertEqual(removed, 2)


# --- 52 retry invents ------------------------------------------------------------------


class DepthRetryInventsNothing(WriterOffEnv):
    def _capture(self, player_input: str, draft: str) -> str:
        seen = []

        def fake_chat(system_prompt, instruction, **kw):
            seen.append(instruction)
            return draft + " The air is cold and smells of wet stone."

        with mock.patch.object(llm, "_chat_text", side_effect=fake_chat):
            llm._retry_narration_prose({}, player_input, {"narration": draft, "scene_plan": {"goal": "Advance the immediate scene"}}, "sys", 30, [], "p", None)
        return seen[0]

    def test_ask_is_modest_and_gives_the_player_line(self):
        ins = self._capture(B_G2_T4_INPUT + "\n\nEngine note: travel east.", B_G2_T1_DRAFT)
        self.assertNotIn("Scene goal", ins)
        self.assertNotIn("Engine note", ins)
        self.assertIn(B_G2_T4_INPUT, ins)
        self.assertNotIn("about 1500", ins)
        self.assertIn("never below 600", ins)
        for needle in ("no new people", "no new lines of speech", "thoughts", "decisions"):
            self.assertIn(needle, ins)

    def test_engine_request_passes_no_player_action(self):
        ins = self._capture("__opening_scene_request__: Establish the immediate situation, include concrete hooks", B_G2_T0_DRAFT)
        self.assertNotIn("__opening", ins)
        self.assertNotIn("concrete hooks", ins)

    def test_live_g2_t0_new_people_rejected(self):
        self.assertTrue(llm._expansion_adds_people_or_speech(B_G2_T0_DRAFT, B_G2_T0_RETRY))
        turn = _turn(B_G2_T0_DRAFT)
        # The live floor was 1000; the 812-character draft was under it.
        with mock.patch.dict(os.environ, {"AI_RPG_MIN_NARRATION_CHARS": "1000"}), \
                mock.patch.object(llm, "_retry_narration_prose", return_value=_turn(B_G2_T0_RETRY)):
            trace: list = []
            out = llm._ensure_narration_depth(turn, {}, "__opening_scene_request__", "sys", 30, [], "narration_depth_retry", trace)
        self.assertNotIn("A child, no more than six", out["narration"])
        self.assertTrue(any(e.get("event") == "depth_retry_rejected" for e in trace))

    def test_live_g2_t1_new_speech_rejected(self):
        expanded = B_G2_T1_DRAFT + B_G2_T1_RETRY_TAIL
        self.assertTrue(llm._expansion_adds_people_or_speech(B_G2_T1_DRAFT, expanded))

    def test_a_known_person_under_another_word_is_not_new(self):
        # Live f3042 g2 t5: the draft's "a man in his fifties" became "the shopkeeper".
        draft = "A man in his fifties, with a thick beard and calloused hands, leans against the counter, watching you."
        expanded = draft + " The shopkeeper drums his fingers on the worn wood, and the bell over the door settles."
        self.assertEqual(llm._expansion_adds_people_or_speech(draft, expanded), [])

    def test_texture_only_passes(self):
        expanded = B_G2_T1_DRAFT + " Dust hangs in the lantern light, and the stagecoach creaks on its springs."
        self.assertEqual(llm._expansion_adds_people_or_speech(B_G2_T1_DRAFT, expanded), [])
        # Reflowed draft speech with the same words is not new speech.
        self.assertEqual(llm._expansion_adds_people_or_speech(B_G2_T1_DRAFT, B_G2_T1_DRAFT.replace("\n\n", " ")), [])


# --- menu closer ------------------------------------------------------------------------


class MenuCloser(unittest.TestCase):
    def test_live_two_choices_menu_and_summary_trimmed(self):
        out = llm._apply_menu_trim(_turn(B_G2_T0_DRAFT))
        self.assertNotIn("You have two choices", out["narration"])
        self.assertNotIn("Each path leads", out["narration"])
        self.assertTrue(out["narration"].endswith("train whistle."))

    def test_summary_sentence_alone_is_not_trimmed(self):
        body = B_G2_T0_DRAFT.split("\n\n")[0]
        text = body + " Each path through the reeds is slick with mud."
        self.assertEqual(llm._trim_menu_ending(text)[1], 0)


if __name__ == "__main__":
    unittest.main()
