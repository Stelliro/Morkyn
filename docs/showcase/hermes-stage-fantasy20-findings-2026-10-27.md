# Hermes 3 8B, 20-turn stage in Thornhallow: do the fantasy100 fixes hold live? (2026-10-27)

Stell: "think you can do the 8b test?"; chose a short stage (~20 turns), log only. Parameters copied from
the fantasy100 run: Hermes 3 (Llama 3.1 8B Q4_K_M), `tools/harness_with_packs.py` -> `api_bridge_playtest.py
--local-model ... --viewer-port 8791`, `AI_RPG_LLAMA_CPP_CONTEXT=16384 AI_RPG_CONTEXT_TOKENS=16384`, setup
`docs/showcase/thornhallow-setup.json`, one Sonnet player from a written brief. Build: `main` at 5b174f4 (the
fantasy100 fixes merged). Evidence in `docs/showcase/hermes-stage-fantasy20-2026-10-27/` (`faults.md`: 41 rows,
`player-notes.md`, `player-brief.md`, `timings.jsonl`); save and traces in the session scratchpad
(`live/stage-fantasy20/`).

## Timing

Setup to opening 54.0 s (post-start passes 33.5 s, opening 20.4 s). Turns: n=19, median 13.0 s, p90 17.5 s,
max 21.1 s; 10.1 model calls a turn. No fallbacks, no stalls.

## The five fixed systems

| System | Result | Turns |
|---|---|---|
| Money only by a stated sum | Held for "no sum = no move": the purse never moved without one. | all |
| Stated payments and sales settle | Mixed. T06 settled (3 copper paid, loaf granted). T05 (an offer of 3 copper, prose takes six and gives three back) moved nothing; the T07 sale moved nothing; prose payouts at T03/T07/T20 never reached the purse. | T05, T06, T07 |
| Jobs filed as said | Held for filing: Q1 Dough Prep filed on the offer, accepted at T03. Still wrong: step 1 marked done at T04 with nothing in the prose; reward drifted from a loaf to "fifteen gold". Payout not tested. | T01-T04 |
| Creature from the prose gets a row | Not really tested: the only creature was a hare the narrator added at T16. Struck at T17: no row, `attack_not_found`, no result line. | T16-T17 |
| Code travel (F210) | T09 `#L2` and T10 worked. T20 `#L2` landed at L1; the note says Verity (@A) is filed at L1 (`attack_target_absent`), so the move may have followed the person's place, not the code. | T09, T10, T20 |

## Other faults seen (not yet triaged)

- S1: the T12 ruin search shows a clay token, iron key and bone scroll case; none reach the inventory, and no
  place is filed for the ruins.
- S1: the starting inventory has no grimoire; Candlelight cost 2 energy (7 -> 5) at T18, not 1; health -1 with no
  injury at T16; travellers filed as duplicate rows (Travelers 1-6, Figure 1).
- S2: T07 invents "a young hedge-mage named Wren" as a separate person who speaks; T11 rewrites the player's
  question.
- S3: engine text (`=== OPS / FOCUS: sensory / SCENE: action`) left in the T06 prose; the Greywold becomes an inn
  "in the shadow of Thornhallow keep" at T11.
- Worked: `!wait 60` at T19 (clock +60, energy +3, the hour in the prose matched).

No fix started. Spot-checked against the turn records: T05, T06, T07, T12, T18, T20 and the T06 leak.
