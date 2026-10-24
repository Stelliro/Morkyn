# Hermes 3 8B, Sonnet as the player: 100 turns in Saltmarrow (2026-10-25)

The second long run on **Hermes 3 (Llama 3.1 8B, Q4_K_M)**, one day after the baseline
(docs/showcase/hermes-base100-findings-2026-10-24.md). Stell's ask: "use the 8b as the model and a smaller
anthropic model as the player and do a 100 turn test, maybe sonnet?" Build: `main` at 977a856 = the baseline
build plus the merged creature-and-bystander fix (24735d1 and its review round 087ee52, merged as 444818d) and
the db migration race fix. Setup: `docs/showcase/saltmarrow-setup.json` (Isk Tarrow), the same scenario as
the baseline. Four **Claude Sonnet** agents played 25 turns each, in character, from a written brief
(`hermes-sonnet100-2026-10-25/player-brief.md`), handing the story over in `player-notes.md`; faults were
logged after every turn and never stopped the run. Run: `tools/harness_with_packs.py` (puts the installed
CUDA pack on the path, then runs `tools/api_bridge_playtest.py --local-model ... --viewer-port 8790`).

Evidence in `docs/showcase/hermes-sonnet100-2026-10-25/`: `faults.md` (212 rows by the four players),
`player-notes.md` (every line typed, the state after each turn, the handovers), `coordinator-notes.md` (the
worst claims checked against the turn records, with the engine-side cause where found), `turn-digest.md`
(`tools/run_digest.py` over all 100 turn records: line, place, gold, inventory delta, dice, engine notes,
prose end), `timings.jsonl`. The save and traces stayed in the session scratchpad (`live/sonnet100/`), served
read-only on port 8790 after the run (`tools/serve_run.py`).

## Timing

| | |
|---|---|
| Setup to opening shown | 17 s (post-start passes 8.4 s, opening 8.5 s) |
| Player turns | n=97, **median 14.3 s**, mean 14.6 s, p90 19.5 s, max 25.5 s |
| Of which | model 14.2 s, GPU wait 0.2 s, engine 0.2 s; 10.4 model calls a turn |
| Wait / sleep turns | n=3, median 19.2 s |
| Fallbacks / retries | none in 100 turns |
| Wall clock, first to last turn | 48 min (Sonnet's reading and logging between turns: median 9.5 s) |

The baseline's median was 11.0 s with the same number of calls; this run is about 3 s a turn slower. Not
investigated (Stell 2026-10-22: issues first, turn time later); the candidates are the merged code's extra
reads and the desktop sharing the GPU.

## Faults

212 rows in 100 turns (89 state, 42 player's agency, 81 prose), 30 of them marked as recurrences; the
players' class labels differ, so the families below are the coordinator's grouping of the rows. Clean turns:
T18, T32, T76, T82, T86, T91, T92 and a handful with one minor row.

| Family | Turns | Severity | What it looks like |
|---|---|---|---|
| **Money never moves by the scene** | T14, T19, T21, T26, T30, T33-34, T52-53, T55-56, T68, T79, T81, T83-85, T87 | S1 | In 100 turns the purse moved four times, none by a scene: a stated -1 while being paid (T19), two quest payouts fired by the parser off a travel sentence and a question (T79, T83), and **+117 from a 6d20+60 die** where the prose said "another fifty" (T84). Every asked trade failed: the medallion sold for two silver ("the money in your hand", T21: `gain_without_coin_dropped`), the candle (T56) and the loaf (T81) bought for two copper with no spend, eleven gold counted onto the ledger (T30, delta empty), fifteen gold tossed in a purse (T52), **eighty silver counted out became the inventory item "eighty silver x1"** (T68), a 20-gold debt payment read as a *gain* and dropped (T87). The silver crown Elric paid was read as a -9 spend and voided (T34). |
| **The narrator speaks, acts and decides for the player** | 42 rows, nearly every turn | S2 | "'Thank you, deputy,' you reply", "You rap on the door", a whole chase (T94), an eight-paragraph scene in third person ("Isk sheathes her knife", T93), a false fact ("My mother, she is a tide-reckoner", T100). The words gate cut many such lines; the ones it kept are the rows. |
| **Scene reset, stranger, hour, pronouns** | ~40 rows | S3 | The trader greets Isk afresh three turns running (T16, T17, T20); a native flat-runner is "traveler" seven times (T27, T44, T54, T58, T70, T72, T77, T97); "the hour before noon" at 08:00, "dawn" at 09:42, "the sun is sinking" at 13:42; Elric is she/he/she across T8-T37 and the engine pinned "he" on a 2:0 count (T36). |
| **The save moves ahead of, or against, the prose** | T5, T6, T17, T37, T45, T54, T66, T77-79, T88-89 | S1 | T5: `where_ended` answered "still in Saltmarrow" (confirmed) and the player was moved to a new "Coast Road" anyway; T6 moved to the lighthouse while "You'll be walking for some time yet"; T66 to a newly minted "Saltmarrow Salvage Yard" while the prose stayed in L4; T77 a duplicate "The Guild Yard" (L10) beside L9; "The marsh" (L11) beside "The Salt Marsh" (L7); "to Saltmarrow" (L12) filed from the line's "to #L1, Saltmarrow". `#L1` ignored twice (T67, T79), honoured twice (T12, T96). No ask-to-move was shown anywhere (not built). |
| **Jobs: filed, but steps are prose and payouts fire wrong** | T4, T9-11, T22-37, T65-68, T79, T83-84, T90 | S1 | Better than the baseline: Q1 was filed (late, T11, after "salvage job x1" stood in as an item from T4) and Q2 in one turn (T29), and both closed once the player asked plainly (T79, T83). But **12 quest steps are narration sentences or the player's own question** ("Who wants what, and what it pays?", "He looks at you, his eyes glinting in the candlelight."), the completion at T79 came off a travel sentence, and Eadric's "Second job's complete too" was `payout_refused unknown_quest` (T84, T90). |
| **People: phantom rows from ops, the tallyman never filed** | T0-3, T5, T14, T38, T51, T54, T56, T58, T63, T65, T79 | S1 | Row A is "Person 1, message runner" for the tallyman of the opening; B Lettice Orme is the same figure; the peddler got three rows (L "= Marcella" with the op's `=` in the name, Avelina Ridley, Marcella); Dunstan, Tamsin, Warin, Reinald Barrow, Clement, Payne, Griselda Stanbury were named by ops and never by the prose; T "Cully ROLE=" carries a field label. Elric's role merges with Eadric's (T31). |
| **Creatures and bodies not filed; the blow lands on a bystander** | T40-48, T60-64, T73-76, T93-94 | S1 | The grave figure became a named orchard keeper "Peregrine" (T40). The feral dog-wolf (T47: "The creature growls ... circles you ... The animal bares its fangs") was asked about as the word **"form"**, judged not hostile, and a melee 19 at "the snarling creature" recorded nothing (T48). The eel-thing was only shown diving (T73), so with no creature on record the stab at "the eel-thing" **hit Delphine [[Q]]** for 1 (T74); it died and was dragged to the bank with no row or body (T75-76). "The man in tattered robes" had no row, so two attacks hit Elric (T93-94). The dead man carried, searched and buried (T46-64) never had a body row; the spade handed over never became an item. |
| **Engine text in prose and in rows** | T13-14, T42, T54, T73, T88, T97 | S3/S1 | **Prose ends with the engine's own rule text**: "Without training, the weapon/tool does as much harm to you as to the world ... Unskilled with Melee: you injure your own hand" (T42, app/skill_checks.py). Inventory "BAND: small x1", "brass x1" (T13-14); event titles "NAME: The Search for the Eel Pool Creature" (T73), "title=" and a gm_event "Consider the options carefully before making a decision." (T88); row names "= Marcella", "Cully ROLE=". |
| Echo of the player's line | T4, T13, T19, T25, T28, T40, T49, T93, T97 | S3 | The line pasted back as the first paragraph or as the player's speech. |
| Smaller | | S1/S3 | Tidecount cost 2 energy twice (T11, T58) and 1 once (T86); a persuasion 2 still got agreement (T90); `!wait 330 wait` with words before it ran as a normal turn and the model's own wait to midnight (T39); the sleep turn narrated as a scene restart (T36) and in past tense (T65); a reply cut at "Ah" (T99); the knife Isk does not own accepted every fight. |

## What worked every time

- **Rest and sleep by `!wait`**: the clock and energy exact every time (T36 +6 h, energy to the cap; T65 2 -> 15, 09:00; T92 +60 min, +3 energy); Tidecount's stated time matched the clock (T86).
- **Travel by `#L` code to a place on record** (T12, T69, T82, T96) and new places minted from the player's own words (Ruined Church, Salt Marsh, Old Ruins, The Quay).
- **Search finds the line asked for reached the inventory** (medallion T13, brass gauge T25, crest medallion from the body T60, the candle T56).
- **`@code` lines**, including two codes in one line (T27 partially, T69 fully).
- **Q2 filed within a turn of the offer** (T29); both quests closed on a plain ask (T79, T83).
- **The engine's voids and refusals**: invented spends voided (T4, T14, T51), a death on a failed roll refused (T42), an invented 10-gold pay dropped (T32), a new person filed only when the prose showed them (Edmund T92, Cully T97).

## Against the baseline

**Two things changed at once**: the build (the merged creature fix) and the player (Sonnet agents, who play and
log differently from the baseline's players). So the raw counts (212 rows against 176) do not say the build got
worse, and "jobs improved" may partly be Sonnet asking for pay more plainly. What holds whoever played: the
turn records checked by the coordinator (coordinator-notes.md): money never moved by a scene, the merged fix
fired on none of this run's three creatures, the moves ahead of the prose, the rule text in the prose. Treat the
family-level findings as reliable and the counts as not comparable; a true measure of a merge keeps the same
player model as the run before it.

Same fault families as 2026-10-24, with these movements:

- **Money is unchanged and is the whole of the state damage that matters to play.** It is the first job: the pre-draft transaction (CLAUDE.md 2026-10-25, TODO m0), then the currency set (m1).
- **Jobs improved**: two filed and completed against zero filed in the baseline; the open class is now the step text (prose sentences as steps) and the payout trigger (a travel sentence pays; the giver's "marked complete" does not).
- **Creatures did not improve** on this run's three creatures: the merged fix needs a kind noun doing a hostile act, and the run gave it a vague noun ("the creature", "the animal", "form"), a creature only seen diving, and an unnamed man. The bystander hits (T74, T93-94) are the worse half: see F192.
- **Moves ahead of the prose** are as frequent as before and now include duplicate place rows; ask-to-move (#46/#76) is still unbuilt.
- **Engine text in the prose** is new in kind (a rule sentence from skill_checks pasted into the narration) and is gate-worthy under the guiding rule.

## Fault log rows

F192-F196 in `run-fault-log-2026-10-18.md` carry the new classes (a vague noun or a seen-only creature leaves
the blow on a bystander; the unskilled-penalty rule text in the prose; coin words filed as items; prose
sentences filed as quest steps; `=`/`ROLE=`/`NAME:` field text in row names and titles). F188 (money), F163
(phantom rows), F156 (jobs), F187 (creatures), F191 (moves) get "(cont.)" notes with this run's turns.
