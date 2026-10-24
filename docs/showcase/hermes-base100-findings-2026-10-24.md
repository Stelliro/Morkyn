# Hermes 3 8B baseline: 100 turns in Saltmarrow (2026-10-24)

The first long run on **Hermes 3 (Llama 3.1 8B, Q4_K_M)**, the model Stell chose on 2026-10-23. Build:
`main` at 5335e93 (0.11.1 plus the engine-written attack line). Setup: `docs/showcase/saltmarrow-setup.json`
(Isk Tarrow, flat-runner, the drowned harbour town, the salvage-guild debt), the same scenario as the Qwen3
8B runs 120-151. Four agents played 25 turns each, in character, handing the story over in
`player-notes.md`; faults were logged after every turn and never stopped the run. Stell's ask: "run a 100
turn test with the 8b model".

Evidence in `docs/showcase/hermes-base100-2026-10-24/`: `faults.md` (every row, one per turn-instance with
"(again Tn, class ...)" marking recurrences), `player-notes.md` (every line typed, the state after each turn,
the four handovers and the run end), `timings.jsonl`. The run's traces and save stayed in the session
scratchpad (`live/base100/`), the save served read-only on port 8790 after the run.

## Timing

| | |
|---|---|
| Setup to opening shown | 42 s (post-start passes 33 s, opening 9 s) |
| Player turns | n=100, **median 11.0 s**, mean 11.4 s, p90 14.7 s, max 26.0 s |
| Of which | model 11.0 s, GPU wait 0.2 s, engine 0.2 s; about 10 model calls a turn (5-16) |
| Fallbacks / retries | none in 100 turns |
| Wall clock, first to last turn | 3 h 26 min (the agents' reading and logging between turns: median 38 s) |

Qwen3 8B on the same scenario (runs 120-141, dev.13): median 26 s, most 16-43 s. Hermes is about twice as
fast with the same number of calls, and never fell back.

## Faults

176 well-formed rows in 100 turns (85 state, 26 player's agency, 65 prose); about 115 of them are recurrences
of a class first seen earlier in the run. No new fault class appeared after turn 50 except one ("narrator
voice: options menu", T77). Clean turns: T5, T10, T11, T20, T96, T98 and a handful with only a minor row.

| Family | Rows | Severity | What it looks like |
|---|---:|---|---|
| Money read from the model's die, not the prose | 19 | S1 | "fifteen silver" paid -> gold +7 (2d6+3); "a single silver coin" -> +7; "for a copper" -> -4; a bed "two silver" -> -24 clamped to 0 (T97). A price said twice in the line and the prose ("two coppers ... two coppers", T84) read as nothing: "two" is a word, not a digit. The engine's voids (T63, T65, T88) were the only brake, and one of them voided the one payment the player asked for. |
| People: identity rebound between rows | 14 | S1/S3 | Row B Mira: hayward's daughter (T1) -> bearded sailor (T4) -> "her" (T6). Row D "Seagulls": a flock (T14) -> the fish-seller (T18) -> a hooded man (T40) -> the eel-fisher, "he", "she", "they"; its code landed on every gull for 86 turns. Rook (I): moved right by `@I` (T89), reset by a model op the next turn, then the tavern keeper, then "she". |
| Unnamed figures not filed, plurals not rolled | 13 | S1 | The dire wolf (T22-T28), a marsh adder, a bog crab, marsh rats, a flock of gulls: **no creature got a row in 100 turns**. A speaking fish-seller (five appearances), a doorman, dockhands, porters, urchins: no rows, no roll. When it worked it worked well: "a pair of guards" -> Guard 1, Guard 2 (T31); "a few patrons" rolled 1d4+1=2 -> "Two patrons", Patron 1/2 (T67). |
| People: phantom rows from ops | 12 | S1 | Every named row of the first 25 turns (A, B, C, E) was filed from an NPC_NEW op before the prose showed the person; T45 Rook filed present from talk alone; T58 "the unnamed figure" minted a duplicate of a woman already filed; T80/T86 a second row for a man already on the page. |
| Agency: the narrator speaks for the player | 12 | S2 | "Isk Tarrow, you say", "I'm passing through" (a false fact against the backstory), "I paid three coppers for it", "'I'll pay,' you say". The agency ask said yes on several and the line stayed. |
| Continuity / scene reset | 12 | S3 | A first meeting replayed with someone met two turns ago ("What business have you with me, stranger?"); the guildhall entered afresh; the tallyman gone and two clerks in his place; the fish-seller re-introduced with a sign. |
| Attack line | 11 | S1 | With no creature row, the blow lands on the bystander: "I ignore Orabel and slash at the dire wolf" -> "Your fist slams into Orabel [[E]]", health 21->17 (T24); "Your fist nicks the figure [[M]]" for a kick at marsh rats (T59). Alone, a swing has no target and no line, and T92 rolled no check at all. One `@E` in a shout was read as the attack's target (T27). |
| Drift | 10 | S3/S1 | The scene told at an inn while the player is in the marsh (T21), the guildhall relocated onto the quay (T31), the marshes crossed between two places inside the town (T99). Twice the engine kept the player where they were (right) and offered no move (the ask-to-move mechanism is not built yet). |
| Echo / leak | 9 | S3 | The player's line pasted back as prose or as the player's speech (T1, T3, T20, T29, T33, T42, T74, T87); nested `[[L1|SALTMARROW [[L1]]]]` markup (T6); the context's own facts pasted ("It's afternoon, 13:08 by the sun. You're wearing leather boots ...", T85); "the human flat-runner" title leak (T99). |
| Jobs / quests | 8 | S1 | **No job a person offered was filed in 100 turns.** The north-docks watch: offered (T11), accepted (T12), confirmed (T32), stood and "paid" (T42) - 0 quest rows (the op was cut with the scene tail at T11, then the parser read the retellings as debt statements or payouts for an unknown quest). The eel job (T73-T80), the debt told as "twenty gold I still owe" (T87): nothing filed. The one quest row of the run ("A debt of bread") was made by the engine's own local_intel offer during a sleep turn and never reached the page. |
| Agency: decides for the player | 7 | S2 | A whole rope purchase and exit for a player who only knocked (T4; the engine voided it, so prose and save split); a payment and a departure for a player who asked what she owed (T9); "You bargain with him and he gives you coin" (T82). |
| Place filing | 6 | S1 | "To North Docks" filed from the op's destination phrase (T13), then a duplicate "North Docks" (T50); "Tide's End Tavern" filed as "Saltmarrow Tavern" (T46), later `#L6` bound by code yet "The Tide's End" minted again as a shore and the player moved there (T89); "the bar" minted as a place inside the tavern (T47). |
| Act stalls | 6 | S3/S2 | The player's purchase, question or ability use re-sets the scene and never happens ("she holds out the fish and quotes the price"; Tidecount applied, reading never stated). |
| Items vs prose, health vs prose, dice | 12 | S1/S3 | Finds not granted (coins, a spoon, a buckle, a jug); a wound applied with the bite cut from the prose (T25); a question containing "a bow" rolled a ranged mishap and cost 1 HP (T56); band labels shown as dice ("item:BAND"). |
| Hour not held | 5 | S3 | "Dawn" at 09:36, 10:51, 13:02 in steady rain; a whole dawn-to-sunrise in six clock minutes. The hour is in facts_to_keep; the prose does not follow it. |
| Agency: the words gate cuts the player's act | 2 (+T11's op) | S2 | "I hand her the coin, take the herring and eat it": the sentences doing exactly that were cut as "the player's words", so the purchase never happened and the turn ended on the seller's question (T17); the QUEST op cut with the tail (T11); the wolf's bite cut, the wound kept (T25). |
| Smaller | 20 | S3 | Whose words are whose (an NPC's line given to the player), roster whereabouts (Esme and Rook walk out, rows stay), "stranger" to a native flat-runner (character facts), padding (a 12-paragraph walk, "The fog seems to..." six times), dice audit noise, "unnamed" and "unconfirmed" roster words leaking into prose. |

## What worked every time

- **Travel** by `#L` code or to a new named place, with a companion's row following (T62, T82, T86, T91, T99).
- **Rest, wait and sleep**: the clock, energy, fatigue, health and the engine's weather all moved together and the prose agreed (T29, T48, T75, T95, T97's sleep).
- **Taking a shown item** when the line asked for it ("I pick up the stones and pocket it", T61; the eels, T81).
- **Refusals that stick** (the rope, T5) and `@`-codes resolving to the right person in talk.
- **Numbered unnamed people** when the mention was read: Guard 1/2, Patron 1/2 with the rolled count written into the prose.
- **The engine's voids** of invented spends (T4, T63, T65, T88): the purse never moved on a model whim; it only failed to move when it should have.

## What the run shows, and the fixes in order

1. **Money must be read from the prose and the line, in base units, by the transaction parser** (CLAUDE.md 2026-10-24: the per-world currency set, `$<number>`, the engine owns the math). Today an amount reaches the purse through the model's GOLD op and a rolled band; the prose's number and the player's own typed price are never read. This is the largest state family and the next job in the agreed order. Number words ("two coppers") must count as numbers.
2. **Creatures and unnamed people the scene shows acting must be filed, and an attack at a thing with no row must never land on a bystander.** Built and under review as this is written (worktree-wf_8923b050-a16-1, 24735d1): the dire-wolf class, the fish-seller class, "Seagulls" as a person row, and the words gate cutting the player's own act.
3. **A person offered a job files it** (F156, reopened with evidence from T11/T32/T42/T73/T87): the QUEST op must survive a tail cut when the player's line accepted; retellings and payouts for "unknown quest" must bind to the open offer by reference (jobs bind by reference, 2026-10-18); a debt the player states to the creditor is a record.
4. **Rows from ops before the prose**: a person is filed when the prose shows them, not when an NPC_NEW op names them (CLAUDE.md: people pencilled in). The run's A/B/C/E phantoms and every rebind (Mira, Seagulls, Rook) start there. The "Seagulls" row shows the kind check must run on op names too.
5. **Ask before an unasked move** (#46/#76, decided, not built): the drift rows where the engine held the player and offered nothing, and T45/T52/T92 where an unconfirmed where_ended answer or a move_from_prose was applied, are the same mechanism.
6. **Speaks for the player**: the agency ask said yes and the sentence stayed on several turns; the measured ask needs its result honoured, or the task made simpler (one sentence, one question).
7. **The hour**: the facts say 13:08, the prose says dawn. A post-draft check against the clock (like where_ended) is the by-class fix; a prompt line is not.

## Fault log rows

F188-F191 in `run-fault-log-2026-10-18.md` carry the new classes (money from the die, the words gate cutting the player's act, the narrator's options menu, unconfirmed where_ended answers applied inconsistently); F156, F163, F181, F185-F187 get "(cont.)" notes with this run's turns.
