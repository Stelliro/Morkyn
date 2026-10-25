# Hermes 3 8B, stage2: 15 turns with a named companion at the fight (2026-10-25)

Second short stage, not a baseline. Build dc1d923 (main with F192-F201 merged). GM: Hermes 3
Llama 3.1 8B Q4_K_M through MLE. Player: one Claude Sonnet agent with
docs/showcase/hermes-stage2-2026-10-25/player-brief.md, told to bring a named companion to the
creature fight (the check stage1 did not reach). Same Saltmarrow setup. Run folder copied to
docs/showcase/hermes-stage2-2026-10-25/ (faults.md, player-notes.md, turn-digest.md, timings.jsonl).

## Timing

| | |
|---|---|
| turns | 15 |
| median turn | 14.9 s |
| mean / p90 / max | 15.3 s / 18.6 s / 30.4 s |
| model / engine per turn | 14.9 s / 0.2 s |
| fallbacks | none |
| wall clock, first to last turn | 6.2 min |

## The fix checks

| Class | Result | Evidence |
|---|---|---|
| F192 bystander hit, companion present | **failed at T11, held at T15** | T11 "stab at the boar": the pre-draft trigger aimed at Wat Thatcher [[E]] (source trigger, no asks), glancing hit, damage 2 on him; the boar got its row only after the draft, the roll was retargeted E->F but his damage stayed and no line was written. T15 "stab at the boar ... Maelis and Reinald stand beside me": aimed at Boar 1 [[F]], damage 1, line "Your blow only grazes the boar [[F]]." |
| F199 creature rows and lines | held | Boar 1 [[F]] numbered and hostile (T11), the engine's line names it by code (T14, T15) |
| F200 places | **failed** | T5 row "to Marsh Edge" (the preposition kept, filed as a place in town); T10 the follow-someone rule moved the player back to Saltmarrow from the prose's "heart of Saltmarrow" on an unconfirmed where-ended answer, the companion left behind (T6 and T7 did not move: the first write-up said T6, the record says otherwise) |
| F201 text notes and echoes | held | no "* NNN chars" line; the first telling of the player's line still appears (by design: it is the asked act), no second telling |
| F193 rule text | held (knife, sword unowned and dropped) | no rule sentence |
| F196 op text | held, one fragment | role "shepherd to" for Jocelin [[D]] (a value cut at a dangling preposition) |
| F194, F195 | not reached | no trade; the one quest's step was the giver's clause (12 words), not refused |

## New faults (verified against the records)

1. **The engine made the player attack** (S2 + S1, T14). The line only led the companions out of
   the gate. The attack ask on Boar 1 replied "Yes, the player is leading Mael..." (a yes that
   restates the line and names someone else) and the second ask, which asks whether the player is
   peaceful, replied "No", so under the two-ask rule the attack counted as confirmed: a melee 17
   was rolled, a combat block built, and "Your blow hits the boar [[F]]." inserted into the prose.
   (The first write-up read the second ask as a disagreeing check; it was not.) Fix agent
   `attack-target2` (with T11): a name only inside a "to <verb>" purpose clause is not asked
   about, and a yes about someone else is no yes.
2. **Money from the model's die** (F188, S1, T1). "You owe me 30 silver" and the player asking
   what they owe: the interpreter's gold-out ask said yes, the engine settled the die's -27, the
   purse was clamped 12 -> 0. T8's -38 die was voided (loss not shown). The pre-draft transaction
   work (m0) is the fix; logged.
3. **A move on an unconfirmed answer** (F191/F200, S1, T10; not T6 as first written). Fix agent
   `place-move2`, with the "to Marsh Edge" name.
4. **People** (F163): Reinald re-cast as a deserter and the reeve, his pronoun flipped to "she"
   (T13-T14), an injured man filed as "Jocelin" with role "shepherd to", Maelis without a row
   until T12. Logged.
5. **The draft contradicts the roll after the line** (S3, T15): "Your blow only grazes the boar"
   then "its eye all but destroyed". The engine's line is in; the narrator's escalation is the
   known contradiction class. Logged.

## What worked

No fallbacks, median turn under 15 s. Companions were filed with codes and stayed on record.
Boar 1 was numbered, hostile and named in the engine's line. The unowned knife and sword
sentences were dropped with notes. Persuasion difficulty was rated per ask. The invented -38 gold
die was voided.
