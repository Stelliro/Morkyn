# Hermes 3 8B, stage1: 15 turns on the build with the sonnet100 fixes (2026-10-25)

A short targeted run, not a baseline. Build 7369a6a (main with F192-F196 merged). GM: Hermes 3
Llama 3.1 8B Q4_K_M through MLE on the RTX 4070 Ti. Player: one Claude Sonnet agent with
docs/showcase/hermes-stage1-2026-10-25/player-brief.md (the five fix checks first). Same Saltmarrow
setup as the two 100-turn runs. Run folder copied to docs/showcase/hermes-stage1-2026-10-25/
(faults.md, player-notes.md, turn-digest.md, timings.jsonl). Stell's rules for this stage: no
100-turn run, Sonnet as the player, Opus agents for the fixes, fix agents never load the 8B.

## Timing

| | |
|---|---|
| turns | 15 |
| median turn | 13.1 s |
| mean / p90 / max | 14.3 s / 23.5 s / 24.1 s |
| model / engine per turn | 14.0 s / 0.18 s |
| fallbacks | none |
| start to opening shown | 35 s |
| wall clock, first to last turn | 5.5 min |

## The five fix checks

| Class | Result | Evidence |
|---|---|---|
| F196 op text in names | held | six person rows and three event titles, none with `=`, `NAME:`, `ROLE=`, `title=` |
| F195 quest steps | held | T2 Q1 "Patch Water Trough Leak", step "patch up a leaking water trough out back"; T4 completed on Dale's "The trough is patched well" and paid |
| F194 coin words as items | held | inventory stayed the four starting items through "five silver", "a copper", "two copper" |
| F193 rule text | held (weakly tested) | two unskilled fist attacks (T12, T13) carried no rule sentence; but no engine attack line was written at all, see below |
| F192 bystander hit | not reached | no named person was present at the fight; instead a new class showed (below) |

## What the run found (verified against the turn records and traces)

Severity counts from the player's table: 31 rows, 16 S1 / 7 S2 / 8 S3. The classes behind them:

1. **A creature named by an op is filed as a person with no kind, and the attacks on it run no
   attack machinery** (new, S1). T11's draft had `NPC_NEW` "Serpent of Saltmarrow"; the kind ask
   answered "A place." (`kind_unread`), the row was filed as a named person at L6, and the one
   sentence that showed the serpent emerging was cut from the prose as a follow-on of the refused
   "silver amulet" gain. T12 "I swing my fist at the creature": check:melee failure 3, prose "Your
   fist connects with the creature's snout with a satisfying thud", health 20 -> 19, and the ledger
   has no attack decision at all (no target, no `attack_target_unknown_noun`, no line). T13 the
   same (failure 3, "your blow connects", 19 -> 18). Fix agent: `creature-attack`.
2. **Places minted from text that is not a place** (F191 family, S1). T4 "I walk back to Dale"
   minted the place "The Dale" from the man's name and moved the player there over a confirmed
   "still in Back Stable Yard" (`where_ended_disagrees` repaired by the venue rule). T6 minted
   "The marshes." (trailing period) beside The Shore and The Deep Marsh. Fix agent: `place-mint`.
3. **Text that is not the story reaches the player** (S3). T7's narration begins "* 850 chars";
   T7 and T9 end with the player's own line pasted back in the second person. Fix agent:
   `prose-echo`.
4. **Money** (F188, known, held for m0): the T4 payout was +15 gold from the parser's die for a
   job offered at five silver; T8's copper and T14's two copper never moved the purse
   (`spend_voided`). Logged, not fixed: the pre-draft transaction work owns this.
5. **People rows** (F163, known): the tallyman filed as "Mattias" from an op (T1), Dale filed as
   "Man 1" (T2) and again as "Dale" (T4), the old woman as "Figure 1" (T7), the gate guard as
   "Olaf" (T14), a name the prose never gave. Logged.
6. **Scene drift** (F191 / ask-before-move, known): T13's marsh lair became "the stable yard"
   with workers and a guard; T14 put the player at "Saltmarrow's south gate". The save correctly
   stayed at The Deep Marsh both times (`where_ended_not_confirmed`). The narrator drift itself
   is the open #33/#46 work. Logged.
7. **Agency** (known class): the narrator voices the player's line ("'I'm looking for work,' you
   say", T1), does the job for them ("Once the patch is dry, you wipe your hands", T3), invents
   their words ("you persist", T8), gives them a weapon ("waving your weapon", T13, noted
   `unowned_weapon_dropped` for the club sentence). Logged; the echo part goes to `prose-echo`.

## What worked

Fast, no fallbacks; every turn wrote a consistent save and a full ledger. The quest pipeline
filed a clean job and paid it on the giver's word. The op parser repairs held. Coin words stayed
out of the inventory. Tidecount charged one energy (T15). The engine refused the invented gold die
(T3, -15 voided), the unowned club, the player's own clothes as items and the unasked silver amulet.

## Next

Merge the three stage fixes when their suites are clean, then another short stage on the 8B with
a named person present at the fight (the F192 check that this run did not reach) and a paid trade,
before anything longer. The money classes wait for m0.
