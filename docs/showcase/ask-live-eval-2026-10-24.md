# Live measurement of the new small asks on Hermes 3 8B (2026-10-24, night fix rounds)

Every ask the round-2 fix branches added, sent through each branch's own prompt builder and `app.llm._chat_text` to Hermes 3 (Llama 3.1 8B, Q4_K_M) on the RTX 4070 Ti, over the real prose of the tester's game (cc87dd29) and the baseline replay. Raw replies and truths: scratchpad live-eval/results.json (not kept in the repo).

# Live eval of the round-2 small asks on Hermes 3 8B (2026-10-23)

**Setup.** Hermes-3-Llama-3.1-8B.Q4_K_M.gguf loaded once per branch process, in-process through the game's MLE path (`runtime_packs.activate()` + CUDA pack, all layers on GPU, context 8192). Every ask went through the branch's own `app.llm._chat_text` with the branch's own prompt builders (`interpreter.ask_*`/`passage_for`/`units`, `entity_kinds.kind_prompt`, `player_agency.*_question`, `where_ended.build_prompt`/`parse_letter`, `turn_checks.*_question`), the branch's system prompt, max_tokens and temperature 0. Replies were parsed with the branch's own parsers. Isolated data dirs only; no repo file edited, nothing committed.

**How it was counted.** Every ask is temperature 0, so each case was asked once and then twice more in shuffled order: the prompt cache depends on what was asked before, and an identical prompt did give two different replies once (the T11 hold_which below). Rates are over all attempts (3 per case). Cases I could not call (marked ambiguous) are left out of the rates and listed. The truth for each case is my own reading of the text. Speed: these asks are tiny. On the 4070 Ti each one took 0.05-0.56 s (mean 0.05-0.29 s per ask type), so speed decides nothing here.

## Per-ask table (branch prompts; `ALT_` rows are other wordings I tested on the same cases, not branch code)
| ask | cases (scored+amb) | attempts | accuracy | false-yes | false-no | unparseable | mean s | max s |
|---|---|---|---|---|---|---|---|---|
| interpreter_died | 23+0 | 69 | 100% | 0/51 (0%) | 0/18 (0%) | 0 | 0.135 | 0.172 |
| interpreter_destroyed | 13+1 | 39 | 100% | 0/30 (0%) | 0/9 (0%) | 0 | 0.128 | 0.147 |
| interpreter_hold | 14+0 | 42 | 64% | 0/18 (0%) | 15/24 (62%) | 0 | 0.118 | 0.169 |
| interpreter_returned | 12+0 | 36 | 100% | 0/27 (0%) | 0/9 (0%) | 0 | 0.129 | 0.152 |
| interpreter_hold_which | 12+0 | 36 | 58% | - | - | 0 | 0.19 | 0.333 |
| interpreter_hold_rewrite | 14+0 | 42 | 36% | - | - | 0 | 0.288 | 0.503 |
| entity_kind | 18+2 | 54 | 100% | - | - | 0 | 0.053 | 0.068 |
| agency_ask_speaks | 13+1 | 39 | 100% | 0/21 (0%) | 0/18 (0%) | 0 | 0.051 | 0.063 |
| agency_ask_voices | 13+0 | 39 | 77% | 3/18 (17%) | 6/21 (29%) | 0 | 0.049 | 0.053 |
| agency_ask_choice | 12+0 | 36 | 100% | 0/18 (0%) | 0/18 (0%) | 0 | 0.058 | 0.066 |
| agency_ask_reply | 11+1 | 33 | 55% | 0/12 (0%) | 15/21 (71%) | 0 | 0.052 | 0.066 |
| agency_ask_retell | 11+2 | 33 | 73% | 3/15 (20%) | 6/18 (33%) | 0 | 0.072 | 0.095 |
| where_ended | 15+2 | 45 | 100% | - | - | 0 | 0.106 | 0.197 |
| check_act | 26+2 | 78 | 65% | 27/36 (75%) | 0/42 (0%) | 0 | 0.082 | 0.192 |
| check_act_pick | 12+0 | 36 | 50% | - | - | 0 | 0.092 | 0.206 |
| check_act_rewrite | 12+0 | 36 | 39% | - | - | 0 | 0.246 | 0.561 |
| ALT_hold_alive | 14+0 | 42 | 79% | 6/18 (33%) | 3/24 (12%) | 0 | 0.124 | 0.151 |
| ALT_hold_says_does | 14+0 | 42 | 93% | 3/18 (17%) | 0/24 (0%) | 0 | 0.124 | 0.17 |
| ALT_which_per_sentence | 52+0 | 156 | 88% | 0/78 (0%) | 19/78 (24%) | 0 | 0.111 | 0.141 |
| ALT_check_even_if_fails | 26+0 | 78 | 74% | 18/36 (50%) | 2/42 (5%) | 0 | 0.084 | 0.241 |
| ALT_check_something_else | 26+0 | 78 | 58% | 6/42 (14%) | 27/36 (75%) | 0 | 0.083 | 0.166 |
| ALT_voices_does_it | 13+0 | 39 | 85% | 0/18 (0%) | 6/21 (29%) | 0 | 0.051 | 0.058 |
| ALT_reply_no_negation | 11+0 | 33 | 100% | 0/12 (0%) | 0/21 (0%) | 0 | 0.065 | 0.082 |
| ALT_retell_only_repeat | 11+0 | 33 | 73% | 6/15 (40%) | 3/18 (17%) | 0 | 0.071 | 0.089 |
| ALT_check_find_sentence | 26+0 | 78 | 73% | 12/36 (33%) | 9/42 (21%) | 0 | 0.079 | 0.172 |

`ALT_check_something_else` asks the question the other way round (truth = "the act is missing"), so its false-yes and false-no columns are swapped compared with the rows above it.

## Verdicts

### Interpreter (branch -1)

- **interpreter_died — KEEP.** 69/69. It said yes on the implied death in T5 ("neck twisted at an unnatural angle"), on T10, on T12 and on baseline T4. It said no on T13 ("let you kill me", she lives), on T8 (the player's line says "blowing her to bits" but the prose has her alive), on 'You: i shoot Marisol' (B3), on a corpse that belongs to someone else, on an imagined death, on a person only mentioned, on a wounded person and on "you'd have to kill me first".
- **interpreter_destroyed — KEEP.** 39/39 on the cases I could call. It said no on a door blown off, a threat, a place only seen from a hill, and a raid that burned three houses. One ambiguous case to watch: for **T5 Thornford** it answered "Yes, Thornford appears to be destroyed" all 3 times. The passage only has flames at its buildings and "a war-torn wasteland", so the city would be recorded destroyed on thin evidence.
- **interpreter_hold — SIMPLIFY.** 64%. It never said yes wrongly (0/18), but it missed **15/24** living cases: T6 ("Beth calls out ... 'Stay safe!'"), T14, T10, B6 and the plain "Beth looks up from her desk and waves you in." Each of those got "No" all 3 times. Misses fail safe (the prose is left as it was), but the hold then does nothing on most turns where it is needed. The premise "<Name> died in turn N" plus "as a living person" seems to steer the model to "no". **Tested replacement:** `Read this.\n\n<passage>\n\nDoes <Name> say or do anything in it? Answer yes or no.` scored **93%**: 0/24 false-no, 3/18 false-yes. All three false-yes were one case, "You remember Beth's laugh, and the way she hummed ...". "Is <Name> alive in it?" did worse: 79%, 6/18 false-yes.
- **interpreter_returned — KEEP.** 36/36. No on every "just alive again" scene, on a ghost and on a rumour. Yes on a ghoul rising, a stimpak revival and a body knitting back together.
- **interpreter_hold_which — SIMPLIFY (one yes/no per sentence).** The pick was exactly right only 58% of the time. Over 36 attempts it made **23 extra picks** and **21 misses**. In T10 it picked the dead-body sentences 12-14 ("Beth's wide, dead eyes stare up ..."), which would then be rewritten or cut. In T14 it picked the scenery (1) and the Jonah sentence (11). In T13 it missed 2, 4 and 6. Wordy replies get cut off at 24 tokens ("Sentences 4, 5, and 10 have Beth speak, acting as a living person. Sentence 9"). The same T11 prompt gave 4,5,10,9 in the case run and 4,5,6,8 in the end-to-end run. **Tested replacement:** one ask per sentence, `Read this.\n\n<paragraph>\n\nIn the sentence "<s>", does <Name> say or do something? Answer yes or no.` It was right on 88% of sentences, with **0/78 false picks** and 19/78 misses (the misses are quiet acts: "frowns", "looks you over warily", "crosses her arms", "leans back"). That is about 0.11 s per sentence, at most 16 sentences per held person.
- **interpreter_hold_rewrite — DROP (cut the sentence instead).** Only 5 of 14 rewrites were usable ("Marisol lies dead, her body still clutching the knife at her belt."). Four replies gave the sentence back unchanged or with only its code removed (T11#8, T11#10, T14#5, B6#4), and `interpreter.rewritten()` has no unchanged-reply check. The others still had her acting: "Beth's lifeless face frowns, clearly puzzled by your actions.", "Dr. Beth's lifeless body leans back in her chair", "Beth, deceased, can be remembered with surprising speed ... as her body grabs a scalpel", "Marisol looks alarmed as you search her dead body.", "Beth's body writhes in agony". **The recheck catches none of this.** It runs the hold ask on the lone rewritten sentence and said "No" on all 14, including the unchanged ones ('"State your business here," she says.' → "No, Beth does not speak"), so every bad rewrite would be applied. If a rewrite is kept at all, it needs an unchanged-reply reject and a recheck with the says/does question on the sentence inside its paragraph.

### Entities (branch -2)

- **entity_kind — KEEP.** 54/54. The T2 fault case "New Vegas" (the player's line plus the prose) came back "place". "Jonah" (tagged [[L1]] in T14) came back "person". The same name both ways (Harrow, Stone) was right in each wording, and so were Millbrook/Ada in one line and the Kessler version of the T2 shape. For information: a creature ("Deathclaw") and a group ("Brotherhood") both came back "place". The engine then only refuses to file them as people, which is harmless.

### Agency (branch -3)

- **agency_ask_speaks — KEEP.** 39/39. Real T7 '"You're not the enemy," you confirm' and T14 '"I'm looking for work ...," you add' got yes. Lines the player hears ('you hear her say', 'You hear Beth shout'), '"..." you are told', '"..." she tells you', remembered words and someone else muttering got no. One ambiguous case: 'You wonder, "What would Beth have done?"' got yes.
- **agency_ask_voices — SIMPLIFY.** 77%. False-yes 3/18: "I'll take it." was accepted for "ask her about the job". False-no 6/21: "Hello there, doc." for "i say hi" and "Thanks, doc. I owe you one." for "i thank her". A false-no drops a line the player actually asked for. The real T14 case ("I'm looking for work ..." for "i say hi") was a correct no. **Tested:** `The player wanted to: <line>\nThe player says: "<q>"\nDoes saying that do what the player wanted?` scored 85%, with **0 false-yes** and the same two false-no. Consider not acting on a "no" for greetings and thanks, or keep the old length rule as the tie-break.
- **agency_ask_choice — KEEP.** 36/36. That includes the real T2 case ("you turn aside ... march west to investigate", after "continue to New Vegas or investigate ...?") and the hesitation and noticing-things negatives.
- **agency_ask_reply — SIMPLIFY (remove the negation).** 55%. **False-no 15/21** and 0 false-yes. It answers "no" to almost everything, including the real T14 case ("So, what kind of work were you thinking about?" after the dropped "I'm looking for work" line) and plain replies ("Ten? Make it fifteen", "The mine? North, past the river"). "The player did not do this:" confuses it. **Tested:** `First: <act>\nThen: <after>\nIs the "then" part an answer to the "first" part? Answer yes or no.` scored **33/33 (100%)**.
- **agency_ask_retell — KEEP (low risk, misses half).** 73%. Its only false-yes (T5 p2/p3) is a pair the engine's overlap gate would never send (2 shared stems). Of the four real pairs that do pass the gate it caught two (T2 p2/p4, T12 p1/p2) and missed two (T2 p1/p2, T8 p1/p2: 'stumbles back, "What the hell?"' twice). A miss leaves the repeat in the prose, as before. "Is passage 2 mostly a repeat of passage 1?" was no better (73%, more false-yes).

### Movement (branch -4)

- **where_ended — KEEP.** 45/45 on the cases I could call. T5 → D (Thornford, marching into its streets). T6 → C (outside, forest). T10, T13, B3, B4 → A (still in the clinic: this is the T13 server-move fault). T2 → outside. T3 and T14 → still in the Sanctuary. Written variants: out of the door → B, out through the gates → C, arriving at Thornford → D, only looking at Thornford's lights → A, only thinking of leaving → A, on the road not there yet → C. Two ambiguous cases: T12 → B ("step out of the fenced area"), and T11 → B. T11's second paragraph has Beth "step out from the clinic" to the player, and it is not a movement turn, so it would not be asked.

### Checker (branch -5)

- **check_act — DROP.** It says yes on almost anything: **false-yes 27/36 (75%)**. It said yes on T7 (aims, then lowers the barrel), T9 (a punch where the line says laser rifle), T13 (no attack at all), T14 (never says hi) and 5 of 7 written misses (knocks instead of picking the lock, a handshake instead of paying, fights instead of fleeing, nods instead of hugging, never searches the drawers). It only caught B3, the climb and the beer. Every other wording I tried also failed: "even if it fails" had 50% false-yes; the inverted question had 75% false-no; "which sentence shows it, or 0" had 33% false-yes and 21% false-no, and those false-no would rewrite correct turns (T5, T6, T8). Keep the branch's removal of the broad verdict, but do not ship this question as the replacement.
- **check_act_pick — DROP (with check_act).** 50%. In T13 it picked Beth's line 10; in T14 the '"Hey!' fragment (3). In V_lock, V_climb and V_hug it picked sentence 1 (scene-setting) instead of the player's wrong act.
- **check_act_rewrite — DROP.** 39% usable. It leaks engine text: "You shoot at @Cbeth." and "Say hi to @Cbeth." (`player_line_of` keeps the @C reference and `turn_checks.plain()` only strips [[..]]), and "The player picks the lock." It writes the player's claimed outcome into the scene: T13 got "Suddenly, you rip her head from her shoulders ... killing her instantly." in front of her talking to you. Once, for B3, it returned a script line: "Marisol: *looks around nervously* I think I hear someone coming...".

## End to end: died then hold, with the real replies

Run through `interpreter.run()` with records like the ones the game had (T11 has the duplicate roster row C "NAME: Beth", which `clean_name` turns into "Beth").

**Tester T10 → T11.** T10: one ask, died(Beth) → "Yes, Beth is dead at the end" → event `died B`. No place in the T10 prose carries a code, so there was no destroyed ask (0.17 s). T11 (12 asks, 2.3 s): hold → "Yes, Beth speaks, moves and acts" → returned → "No" → which → "Sentences 4, 5, and 6 ... Sentence 8". These numbers differ from the standalone run of the same prompt. Then four rewrites, each passed by a lone-sentence recheck answering "No.":
- #8 came back the same with only the code removed;
- #6 became "Her words are firm, with an edge of warning in her voice. Beth is dead.";
- #5 lost its quote marks and gained a body: "Beth's lifeless body lay motionless on the floor, her eyes vacant and staring. You're looking for something? I don't have anything to give or sell. Now state your business, or leave.";
- #4 became "Beth's lifeless face frowns ...".

Then the died ask ran over the rewritten text for the **living duplicate C** (named by name, because B is no longer in the living list) → "Yes" → event **`died C`**. **Net effect:** Beth B stays recorded dead (good). The prose still has her frowning, stepping out of the clinic, regarding you and saying "State your business here," and now reads worse. A second roster row is recorded dead.

**Baseline T4 → T5** (trace files 000004 and 000005). B4: died(Marisol) → yes → `died A`; destroyed(Sanctuary) → no; destroyed(Clinic) → no (0.38 s). B5 (7 asks, 1.1 s): hold → yes, returned → no, which → "3 and 4" (correct). #4 became "Marisol lies dead, her body still clutching the knife at her belt." (good). #3 became "Marisol looks alarmed as you search her dead body." (still alive), and the recheck "No. In the text, Marisol" let it through. Final prose: "... Marisol looks alarmed as you search her dead body. Marisol lies dead, her body still clutching the knife at her belt." The record stays right; the prose is half repaired.

**Conclusion for the pair.** died is reliable and records the death. hold mostly misses (the replacement fixes that). Once hold fires, the which → rewrite → recheck chain is where the prose damage comes from. Change the pair to: say/does hold, per-sentence pick, cut (no rewrite). Also, the died ask should not run on a living record whose name was only matched after the dead record with the same name was held. That is an engine fix, not a prompt fix.

## Other findings

- **Greedy is not fully fixed.** The same prompt (T11 hold_which) gave two different number lists depending on what came before. Repeats showed this in T10 which, T13 pick and three check_act_rewrite cases. Answers that act on state should not assume one fixed reply per prompt.
- **Sentence splitting** (`prose_state.sentence_spans`, used by the checker and interpreter) cuts quotes into pieces ('"What the hell?"' / 'she exclaims, hands raised.'; '"Back so soon?"' / 'Beth asks from the doorway.'). The numbered lists the model sees are then out of step with who is speaking.
- **No reply was unparseable.** Every reply started with yes/no, a letter, a number or person/place. Long replies ("Yes, Beth is dead at the end ...") are cut off at 8 tokens, but the first word survives.

Files: results.json (every case: prompt, raw reply, parsed answer, truth, seconds, the 2 repeats; the end-to-end runs with their calls), summary.json, out/*.json and out/*.log, and the scripts run_*.py.

---

# Round 2 of the measurement: the asks round 3 added (merged main 3f3471a)

Same harness (the merged code's own builders, `app.llm._chat_text`, temperature 0, 3 shuffled passes per case, 0.05-0.21 s per ask). Raw replies: scratchpad live-eval-2/results.json.

| ask | scored cases | accuracy | false-yes | false-no | verdict |
|---|---|---|---|---|---|
| interpreter_died_check ("Is <Name> alive at the end of it?") | 26 | 96% | 0/27 | 3/51 | KEEP (never blocked a true death) |
| interpreter_destroyed_check ("Is any of <Name> still standing?") | 14 | 64% | 0/9 | 15/33 | KEEP only as the gate after a destroyed yes (T5 Thornford blocked 3/3) |
| interpreter_hold ("Does <Name> say or do anything in it?") | 17 | 94% | 3/24 | 0/27 | KEEP (its false-yes is a player's own memory sentence, never cut) |
| interpreter_returned_check | 16 | 94% | 3/30 | 0/18 | KEEP |
| interpreter_hold_which (one sentence at a time) | 56 | 89% | 0/72 | 19/96 | KEEP (never a false cut; misses quiet acts: frowns, crosses her arms) |
| where_ended letter (old wording) | 24 | 75% | - | - | changed to the "you" wording: 92% |
| where_ended confirm (the answer put back) | 68 | 41% | 54/132 | 12/72 | **replaced**: it echoed the label (T11 walked out of the clinic 3/3) |
| where_ended confirm, "are you still in <here>?" | 24 | 92% | 6/27 | 0/45 | merged: 0 wrong moves in 72 |
| quote_speaker ("does a person say") | 14 | 86% | 6/21 | 0/21 | **replaced**: a written note and graffiti counted as speakers |
| quote_speaker, "is \"...\" spoken by someone?" | 14 | 100% | 0/21 | 0/21 | merged |
| place_going | 19 | 95% | 3/27 | 0/30 | KEEP ("I point to the clinic" still counts as going) |
| agency voices / could_say / own_act | 18 / 18 / 14 | 83% / 94% / 93% | 0 / 3 / 3 | 9 / 0 / 0 | KEEP |

Pairs as the engine uses them (a fact recorded only when the first ask says yes and the check agrees): died + died_check 81/81, destroyed + destroyed_check 42/42, returned + returned_check 48/48; where_ended letter + the new still-here check: 60 right actions, 0 wrong moves, 12 no-actions in 72 (the old pair made 15 wrong moves).

Also found: a place row named "None" was offered as "A) still in None" (#163's placeholder ops; now never offered), and `interpreter.units` keeps a quote apart from a speech tag that opens on a capitalised name ('"Back so soon?"' / 'Beth asks ...').

---

# Rounds 4 and 5 of the measurement: the dead-body asks and the unnamed-figure asks (2026-10-24)

Same harness. Raw replies: scratchpad live-eval-4/ and live-eval-5/results.json.

**Body asks** (branch e26f756), 28 + 6 cases:

| ask | accuracy | false-yes | false-no | verdict |
|---|---|---|---|---|
| body_here ("Is X's body with the player at the end of it?") | 92% | 3/24 | 3/51 | KEEP |
| body_here_check ("Has the player left X's body behind?") | 59% | 25/51 | 6/24 | **replaced** by "Has the player walked away from X's body?" (27/27 on death turns, 0 false facts) |
| body_buried ("Is X's body buried?") | 92% | 8/84 | 0/15 | **replaced** by "Is X's body in a grave?" (97%; the acid pit is no longer a burial) |
| body_buried_check ("Can X's body be seen?") | 86% | 3/24 | 9/60 | KEEP |
| body_carried ("Is the player carrying X's body?") | 64% | 36/90 | 0/9 | **replaced** by "Is X's body in the player's arms or over the player's shoulder?" (96%) |
| body_carried_check ("Is X's body lying on the ground?") | 68% | 15/36 | 9/39 | KEEP (with the new carried ask) |

Body outcomes as the engine reads them: 76.4% with the first wordings, 95.8% with the replacements.

**Unnamed-figure asks** (branch f3d3620), 29 cases:

| ask | accuracy | unparseable | verdict |
|---|---|---|---|
| figure_kind ("is X a person, an animal or a monster?") | 44% | 42/75 | **replaced**: a choice question, cut off at 4 tokens before any answer; "is X a being that can act on its own?" 100% |
| figure_kind_check ("could the player fight or talk to the X?") | 53% | 0 | **replaced**: said no to nearly every true figure; "could you fight or talk to the X? Answer yes or no." 93%, 0 false yes |
| figure_hostile ("does X attack or threaten the player?") | 100% | 0 | KEEP |

The reviewer's fear (a yes-leaning 8B filing "Ping 1" and "Counter 1" as hostile figures) was the wrong way round: on these asks Hermes did not lean yes, it failed to answer, so the branch as written filed no figures at all, real or phantom. The replacement pair: 89%, 0 false files.

Lessons: a question that offers a choice is not a yes/no question, and a 4-token cap cuts the 8B off while it restates the question; "Answer yes or no." at the end does most of the work for a yes/no; a "left behind" or "carrying" word in a question is read loosely, so ask for the physical fact ("walked away from", "in the arms or over the shoulder", "in a grave").

## Round 9: "did the player's line ask to go?" (the drift re-draft's gate, F184)

Hermes 3 8B, temperature 0, 4 tokens, the player's line only. 42 moving lines (the reviewers' corpora,
including the gerund and "my way out" lines the engine rule missed) and 33 staying lines (attack,
search, talk, trade, the recorded drift turns).

| Ask | Moves read right | Stays read right |
|---|---|---|
| `Does the player go to another place?` | 35/42 (missed: "walk over to the bar", "go up to my room", "limp back to camp" x2, "attack ... while backing out of the room", "attack while advancing to the gate", "ask Mara to take me to the clinic") | 27/33 (yes on "i search the dead ghoul", "i shoot Dr. Vasilis", "tell the guard I'm going to the docks later") |
| `Does the player stay where they are?` | 40/42 | 18/33 (no on most attacks: "i shoot the closest ghoul", "I punch the guard") |

Verdict: neither ask can gate a re-draft. A missed move re-drafts the player back in place, and the
"go" ask misses 1 in 6. Stacking both asks with the engine rule stops every wrong re-draft in this
corpus but also skips all three recorded true drifts. The re-draft stays off. The drift goes to
the ask-to-move mechanism (#46/#76, Stell 2026-10-24) instead: when the scene ends somewhere the
line did not go, offer the move. A misread there costs the player one question, not their move.
Script and replies: scratchpad live-eval-9/run.py, results.json.
