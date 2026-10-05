"""
Playtest #29 and #30 (live Qwen3 8B smoke run, round 2 with the launcher env).

Every narration string below is copied from the live run (scratchpad\\smoke):

  #29  g1_turn1.json final narration: each paragraph restarted on the last line
       of the one before ("He leans in, his voice low." / "He hands you a small
       data crystal."), and P1 was cut at the 480 cap inside a quotation.
       turn-000003 ledger: write 1 opened with write 0's last two sentences
       and a stray quote mark.
  #30  turn-000006 draft_dsl response: the draft wrote the player's replies
       ('You shake your head. "Just checking what you have to offer."') for
       an input with no speech in it. run1\\g1_turn2.json (pipeline off):
       '"I don't think," you say, stepping forward. "I know."' for
       "Rolf, come with me. ..." reached the player.

Covered:
  (a) the beat writer gets only the previous paragraph's last line, once, and
      is told not to repeat it; the brief carries no second 400-char copy;
  (b) a paragraph that opens on the previous paragraph's last sentences loses
      them at any length; a short echo elsewhere stays;
  (c) the cap cut never lands inside a quotation, and curly closers end a
      sentence; an unclosed quote counts as truncated;
  (d) the draft and writer asks carry the player boundary and player_line,
      and the draft length scales with the action;
  (e) the writer never sees draft lines invented for the player;
  (f) invented "you say" speech is dropped from the finished turn on every path
      and recorded in self_check.
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-live-echo-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
        "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    }
)
LAUNCHER_ENV = {
    "AI_RPG_NARRATION_PIPELINE": "1",
    "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1",
    "AI_RPG_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}
_launcher_patch = mock.patch.dict(os.environ, LAUNCHER_ENV)


def setUpModule():
    _launcher_patch.start()


def tearDownModule():
    _launcher_patch.stop()


from app import llm  # noqa: E402
from app.narration_pipeline import (  # noqa: E402
    NarrationLedger,
    _quote_marks,
    build_paragraph_briefs,
    drop_repeated_sentences,
    looks_truncated,
    polish_paragraph,
    run_narration_pipeline,
)
from app.prompts import PROSE_VOICE  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT, build_dsl_user_prompt  # noqa: E402

# R2 g1 turn 1, final narration_segments.
G1_T1_INPUT = "Umar, who is waiting for me in the clinic? I don't remember agreeing to meet anyone."
G1_T1 = [
    "You step off the platform and into the med-bay, the air thick with the scent of antiseptic and the hum of machines. Umar Mendes is waiting by the far end of the room, his face lined with worry. He’s not the kind of courier who delivers messages; he’s the kind who carries secrets. You remember now—there was a note in your pack, slipped between your belongings, asking you to meet him here. He leans in, his voice low. “The Guild’s watching the docks.",
    "He leans in, his voice low. They think you’re heading there, but you’re not. You’re heading to the Starborn Rebellion.” He hands you a small data crystal. “This is your next lead.",
    "He hands you a small data crystal. “This is your next lead.” His fingers tighten around it, the metal cool against his palm, as if he’s already preparing to let it go. You glance at the far end of the room where the machines hum and the antiseptic scent lingers—Umar’s worry etched into every line of his face. He doesn’t ask if you’re ready. He just waits, like the whole thing was always meant to happen, and you’re already too far in to turn back.",
]
# R2 g2 turn 2 ledger, writes 0 and 1.
G2_T2_W0 = "You push past the frostbitten door of The Frostbound Crossroads, the air sharp with the scent of woodsmoke and iron. Whitney Garcia, the nurse, looks up from her cot, her hands still stained with antiseptic. “You're not going to stop him, are you?” she asks, her voice a mix of exhaustion and concern. You nod, stepping into the thin, frigid light of the morning. The streets are empty, save for the rhythmic clatter of a bike courier’s bell in the distance."
G2_T2_W1 = "\"You nod, stepping into the thin, frigid light of the morning. The streets are empty, save for the rhythmic clatter of a bike courier’s bell in the distance. Whitney’s gaze lingers on you a moment longer, her fingers brushing the edge of her cot as if steadying herself."
# R2 g2 turn 5 (trace turn-000006), draft_dsl response, ===NAR===.
G2_T5_INPUT = "I give up on Carlos for now, walk back to the Chrome Wrench Garage and go inside to see what they sell."
G2_T5_DRAFT = (
    "You leave the Forest Path and head east, the gravel crunching under your boots. The Chrome Wrench Garage comes into view, its metal frame weathered by time and the elements. You push through the creaking door, the scent of oil and rust filling your nostrils. Inside, the garage is dimly lit, with tools hanging from the ceiling and a few workers scurrying about. You approach the counter, where a burly man with a beard and calloused fingers is wiping his gloves.\n\n"
    "\"Looking for anything specific?\" he asks, his voice gravelly.\n\n"
    "You shake your head. \"Just checking what you have to offer.\"\n\n"
    "He nods, then turns to a shelf behind him. \"We’ve got a few things for sale. Some parts for bikes, some for engines. You’re not looking for a bike, are you?\"\n\n"
    "You glance at the bikes leaning in the corner, their frames rusted but still intact. \"Not exactly. I’m more interested in what you can fix.\"\n\n"
    "He grins, wiping his gloves on a rag. \"Well, I can tell you’re not the only one with a problem. We’ve got a few customers in and out all day. You’ll have to wait your turn.\""
)
# R1 g1 turn 2 (pipeline off), final narration around the invented line.
R1_G1_T2_INPUT = "Rolf, come with me. I want to find whoever is burning those herbs down by the huts before they slip away."
R1_G1_T2 = [
    "Rolf [[A]] stops beside you, his gaze fixed on the smoke curling into the sky, his face shadowed by the brim of his hat. The smoke is controlled, deliberate, as if someone is using the flames to signal or to conceal.",
    "“You think they’re still there?” he asks, his voice low, almost a whisper against the wind.",
    "“I don’t think,” you say, stepping forward. “I know.”",
    "The ground beneath your feet is uneven, littered with fragments of charred leaves and brittle twigs.",
]
CAP_PARA = (
    "You step off the platform and into the med-bay, the air thick with the scent of antiseptic and the hum of machines. "
    "Umar Mendes is waiting by the far end of the room, his face lined with worry. He's not the kind of courier who delivers "
    "messages; he's the kind who carries secrets. You remember now, there was a note in your pack, slipped between your "
    "belongings, asking you to meet him here. He leans in, his voice low. “The Guild's watching the docks. They think "
    "you're heading there, but you're not.”"
)


def _capture_writer(previous: str, brief: dict | None = None):
    captured: dict = {}

    def fake_chat(system, user_prompt, **kwargs):
        captured["system"] = system
        captured["payload"] = json.loads(user_prompt)
        return "The garage smells of oil and old rubber."

    writer = llm._make_pipeline_paragraph_writer([], [], 60, {})
    with mock.patch.object(llm, "_chat_text", side_effect=fake_chat):
        writer(brief or {"beat_index": 2, "beat_role": "act", "model_limits": {}, "draft_slice": "x"}, previous, NarrationLedger(1, "", {}))
    return captured


class TailEchoAskTests(unittest.TestCase):
    """#29-tail-echo-ask."""

    def test_writer_gets_only_the_last_line_once(self):
        previous = G1_T1[2]
        captured = _capture_writer(previous)
        payload = captured["payload"]
        self.assertNotIn("previous_paragraph_tail", payload)
        line = payload["last_line_already_written"]
        self.assertTrue(previous.endswith(line))
        self.assertLessEqual(len(line), 160)
        self.assertLess(len(line) / len(previous), 0.4)
        self.assertNotIn("Continue from previous_paragraph_tail", captured["system"])
        self.assertIn("never repeat or restate last_line_already_written", captured["system"])

    def test_pipeline_brief_has_no_second_copy(self):
        seen: list[dict] = []

        def stub_writer(brief, previous, ledger):
            seen.append(dict(brief))
            return G1_T1[2] if brief["beat_index"] == 1 else "Rain ticks on the tin roof while the machines keep humming along the far wall."

        run_narration_pipeline({}, "I look around the med-bay.", writer=stub_writer, turn_number=2)
        self.assertGreaterEqual(len(seen), 2)
        self.assertFalse(any("previous_paragraph_tail" in brief for brief in seen))


class ShortEchoTests(unittest.TestCase):
    """#29-short-echo-survives."""

    def test_live_g1_t1_restarts_are_dropped(self):
        kept, dropped = drop_repeated_sentences(list(G1_T1))
        self.assertFalse(kept[1].startswith("He leans in, his voice low."), kept[1])
        self.assertFalse(kept[2].startswith("He hands you a small data crystal."), kept[2])
        self.assertNotIn("This is your next lead", kept[2])
        self.assertIn("His fingers tighten around it", kept[2])
        self.assertIn("He leans in, his voice low.", dropped)

    def test_live_g2_t2_echo_and_stray_quote_go(self):
        kept, dropped = drop_repeated_sentences([G2_T2_W0, G2_T2_W1])
        self.assertTrue(kept[1].startswith("Whitney’s gaze lingers"), kept[1])
        self.assertEqual(_quote_marks(kept[1]) % 2, 0)

    def test_short_echo_away_from_a_boundary_survives(self):
        paras = [
            "“I know,” he said. The door shuts behind the courier and the room goes quiet.",
            "Rain drums on the roof of the clinic. “I know,” he said.",
        ]
        kept, _ = drop_repeated_sentences(paras)
        self.assertIn("“I know,” he said.", kept[1])

    def test_finished_turn_drops_the_restart(self):
        turn = {
            "narration": "\n\n".join(G1_T1),
            "narration_segments": [{"label": "paragraph", "text": t} for t in G1_T1],
            "self_check": {"corrections_made": []},
        }
        out = llm._drop_repeated_sentences_in_turn(turn)
        texts = [seg["text"] for seg in out["narration_segments"]]
        self.assertFalse(texts[1].startswith("He leans in"))
        self.assertFalse(texts[2].startswith("He hands you"))


class CapCutQuoteTests(unittest.TestCase):
    """#29-cap-cut-inside-quote."""

    def test_cap_cut_never_leaves_an_open_quote(self):
        self.assertGreater(len(CAP_PARA), 480)
        out = polish_paragraph(CAP_PARA, 480)
        self.assertEqual(_quote_marks(out) % 2, 0, out)
        self.assertTrue(out.endswith("his voice low."), out)

    def test_curly_closer_is_a_sentence_end(self):
        text = (
            "He says, “This is your next lead, and it is the only one you will get from me tonight.” "
            "More words follow here and run on " + "on " * 200
        )
        out = polish_paragraph(text, 160)
        self.assertTrue(out.endswith("tonight.”"), out)

    def test_unclosed_quote_is_truncated(self):
        self.assertTrue(looks_truncated(G1_T1[0]))
        self.assertFalse(looks_truncated("He looks up. “Go now.”"))
        # Under the cap, an open quote is trimmed back to the last balanced end.
        out = polish_paragraph(G1_T1[0], 480)
        self.assertEqual(_quote_marks(out) % 2, 0, out)


class DraftAskTests(unittest.TestCase):
    """#30-draft-invents-player-lines."""

    def test_prompts_state_the_player_boundary(self):
        self.assertIn('all that "you" say and do this turn', PROSE_VOICE)
        self.assertIn("leave the answer to the player", PROSE_VOICE)
        self.assertIn("player_line is the player's own input", DSL_SYSTEM_PROMPT)
        self.assertNotIn("about 1000-1800 characters, natural", DSL_SYSTEM_PROMPT)

    def test_draft_request_carries_player_line_and_scaled_length(self):
        packet = json.loads(build_dsl_user_prompt({}, G2_T5_INPUT))
        self.assertEqual(packet["player_line"], G2_T5_INPUT)
        self.assertEqual(packet["narration_length"], "about 1000-1500 characters")
        short = json.loads(build_dsl_user_prompt({}, "I open the door."))
        self.assertEqual(short["narration_length"], "about 1000-1200 characters")
        opening = json.loads(build_dsl_user_prompt({}, "__opening_scene_request__"))
        self.assertNotIn("player_line", opening)
        self.assertEqual(opening["narration_length"], "about 1000-1800 characters")


class WriterBoundaryTests(unittest.TestCase):
    """#30-writer-keeps-draft-player-lines."""

    def _briefs(self):
        budget = {"paragraphs": 3, "beat_roles": ["establish", "act", "pressure"], "chars_per_paragraph": {"min": 320, "max": 480}}
        return build_paragraph_briefs(budget, {}, G2_T5_INPUT, NarrationLedger(6, G2_T5_INPUT, budget), "", draft={"narration": G2_T5_DRAFT})

    def test_draft_lines_invented_for_the_player_never_reach_the_writer(self):
        briefs = self._briefs()
        joined = " ".join(b.get("draft_slice", "") for b in briefs) + briefs[0].get("scene_draft", "")
        self.assertNotIn("Just checking what you have to offer", joined)
        self.assertNotIn("more interested in what you can fix", joined)
        self.assertIn("Looking for anything specific?", joined)
        self.assertIn("wait your turn", joined)
        self.assertTrue(all(b.get("player_line") == G2_T5_INPUT for b in briefs))

    def test_writer_ask_names_player_line_and_narrows_keep(self):
        brief = self._briefs()[1]
        captured = _capture_writer(G2_T2_W0, brief)
        self.assertIn("player_line is the player's own input", captured["system"])
        rules = " ".join(captured["payload"]["rules"])
        self.assertNotIn("keep its speakers and facts", rules)
        self.assertIn("comes only from player_line", rules)
        self.assertEqual(captured["payload"]["brief"]["player_line"], G2_T5_INPUT)


class InventedSpeechCheckTests(unittest.TestCase):
    """#30-no-structural-check-for-invented-player-speech."""

    def _turn(self, paras):
        return {
            "narration": "\n\n".join(paras),
            "narration_segments": [{"label": "paragraph", "text": t} for t in paras],
            "self_check": {"corrections_made": []},
        }

    def test_live_r1_invented_reply_is_dropped_and_recorded(self):
        out = llm._drop_invented_player_speech(self._turn(R1_G1_T2), R1_G1_T2_INPUT)
        self.assertNotIn("I don’t think", out["narration"])
        self.assertNotIn("I know.", out["narration"])
        self.assertIn("You think they’re still there?", out["narration"])
        self.assertTrue(any("did not say" in c for c in out["self_check"]["corrections_made"]))
        self.assertEqual(len(out["narration_segments"]), 3)

    def test_live_draft_reply_is_dropped_on_the_pipeline_off_path(self):
        paras = G2_T5_DRAFT.split("\n\n")
        out = llm._drop_invented_player_speech(self._turn(paras), G2_T5_INPUT)
        self.assertNotIn("Just checking what you have to offer", out["narration"])
        self.assertIn("Looking for anything specific?", out["narration"])
        self.assertIn("We’ve got a few things for sale", out["narration"])

    def test_the_players_own_words_stay(self):
        said = 'I tell him "Rolf, come with me."'
        paras = ["“Rolf, come with me,” you say, already walking toward the huts."]
        out = llm._drop_invented_player_speech(self._turn(paras), said)
        self.assertIn("Rolf, come with me", out["narration"])
        plain = llm._drop_invented_player_speech(self._turn(paras), R1_G1_T2_INPUT)
        self.assertIn("Rolf, come with me", plain["narration"])

    def test_indirect_speech_and_npc_lines_are_left_alone(self):
        paras = ["“What about the docks?” you ask. The keeper shrugs."]
        out = llm._drop_invented_player_speech(self._turn(paras), "I ask the keeper about the docks.")
        self.assertIn("What about the docks?", out["narration"])
        npc = ["You offer him the coin. “Fair enough,” he says, pocketing it."]
        out = llm._drop_invented_player_speech(self._turn(npc), "I pay the man.")
        self.assertIn("Fair enough", out["narration"])


if __name__ == "__main__":
    unittest.main()
