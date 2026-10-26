# Hermes 3 8B, Sonnet as the player, a random theme: 100 turns in Thornhallow (2026-10-26)

The first 100-turn run on the **full contract** (context 16384) with the sonnet100, stage1 and cheat100 fixes
in (F192-F196, F199-F201, F203-F209) and m1 (the currency set, the purse in base units). Stell's ask: "use most
recent chat for parameters for a 8b 100 turn full spectrum playtest with random theme". So: the cheat100 run's
parameters (Hermes 3, Llama 3.1 8B Q4_K_M; `tools/harness_with_packs.py` -> `api_bridge_playtest.py
--local-model ... --viewer-port 8790`; `AI_RPG_LLAMA_CPP_CONTEXT=16384 AI_RPG_CONTEXT_TOKENS=16384`; four Claude
Sonnet players, 25 turns each, from a written brief, handing the story over in `player-notes.md`), but played
**straight** (not a cheat run) across every system, on a theme rolled at random from the setup page's preset
list (seed 1792980795 -> **fantasy**; Saltmarrow's "salvage" excluded). Build: `main` at 084c3f0 (= dee4eed plus
the setup file). Setup: `docs/showcase/thornhallow-setup.json`: Wren Ashcombe, a hedge-mage's apprentice in a
border town of the kingdom of Aldmere, owing the Chandlers' Guild; one spell (Candlelight, 1 energy); copper /
silver / gold.

Evidence in `docs/showcase/hermes-fantasy100-2026-10-26/`: `faults.md` (126 rows by the four players),
`player-notes.md` (every line typed, the state after each turn, the handovers), `coordinator-notes.md` (each
player's three worst claims checked against the turn records, with the engine-side cause), `turn-digest.md`
(`tools/run_digest.py` over all 100 turns), `timings.jsonl`, `player-brief.md`. The save and traces stayed in the
session scratchpad (`live/fantasy100/`).

## Timing

| | |
|---|---|
| Setup to opening shown | 27.0 s (post-start passes 18.0 s, opening 8.9 s) |
| Player turns | n=96, **median 12.9 s**, mean 14.2 s, p90 19.7 s, max 31.8 s (T11) |
| Of which | model 13.8 s, GPU wait 0.2 s, engine 0.2 s; 11.0 model calls a turn |
| Wait / sleep turns | n=4, median 13.2 s |
| Fallbacks / retries / stalls | none in 100 turns |
| Wall clock, first to last turn | 40 min (Sonnet's reading and logging between turns: median 8.2 s) |

Faster than sonnet100 (median 14.3 s) and cheat100 (14.4 s) on the same hardware, with the full contract.
Not investigated (Stell 2026-10-22: issues first, turn time later).

## Faults

126 rows in 100 turns (61 state, 17 player's agency, 48 prose). Eight clean turns (T1, T26, T27, T34, T35, T44,
T61, T64). The counts are lower than sonnet100's 212 and cheat100's rows, but a different world, a different
player set and a different build; **the families are what compare**, and every open family is still here.

| Family | Turns | Severity | What it looks like |
|---|---|---|---|
| **Money from the band die, not the prose** (F188) | T8, T11, T32, T45, T49, T50, T53, T62, T98 | S1 | The purse went 12 -> 56 gold in 100 turns and not one of the moves was the sum the scene showed. T11: a question about a loaf for three copper, purse -11 (`gold_delta 2d6+3 = -11`, interpreter `out: true`, no reader hit). T32: offering to sell the loaf for four copper, Gisela counters six, nothing sold, purse **+12** (the void step only voids unconfirmed *losses*; an unconfirmed band gain goes through). T53: "I offer the clerk 10 silver toward the debt", she takes it, purse **+13** (the interpreter answered `out: true` and `in: true` at once; the die decided). T62: an old coin picked up became +1 gold. T98: "I will sell him the dried meat tomorrow" removed the meat (`item:dried 1`, turn_bands), no coin. The die's losses were voided every other turn (T45, T49, T50, T88: `spend_voided`), so the die still rolls and still tries. |
| **Stated payments and sales never settle** (F156, F194) | T10, T12, T17-19, T33, T48-49, T55, T81-82, T88, T94, T96 | S1 | T19 "one silver coin ... on the debt": handed over in prose, `payment_unpriced_banded -small` then voided; the denomination was not read. T33 the loaf handed to Gisela "Fair deal": bread still held, no six copper. T48 Gisela upends a pouch into Wren's palm, T49 "fifteen of them": `gain_without_coin_dropped "the prose shows no coin reaching the player"`. T81 "two silver, Roger, and it is yours", Roger agrees and pockets the meat: delta empty. T88 two copper for ale: voided. T94 "pay me the eight gold we agreed", Edith counts out eight: the parser paid **Q1's recorded 15** and read the stated eight as a *loss*. What did settle: T12 the loaf at the countered six copper (purse -6 copper, bread added; the prose showed no sale) and T55 / T96 five and ten silver to the guild (`prose_paid`, purse_units -500 / -1000, the integer `gold` mirror unmoved). The debt itself is on no record: three clerks quoted "9 gold", "14 silver" and "a silver sovereign per week". |
| **Jobs filed from chatter, paid off a chore, closed by record** (F195) | T5, T7-9, T29, T49, T55, T62, T70, T83, T89-94 | S1 | Q2 "helping hands" from "There's always need for helping hands" (T5); Q3 "Floor-cleaning" filed **and paid 15 gold in the same turn** off "I take the broom and sweep" with no pay in the prose (T8), then Roger quoting "15 gold pieces for today's sweep" as still owed (T9); Q4 "Seek Hidden Knowledge" from a stranger's remark, later `declined` without an offer (T29, T33); Q5 from "a name to ask after"; Q6 "cut firewood" filed on a **sleep turn** (T70). Two quest steps filed with no quest row (T55, T62). The job Wren did accept twice (T7 sweeping at the inn; T90 Edith's stables at eight gold) got **no row of its own**: T94's payout went to Q1 "skilled labor", a notice-board slip, whose step had jumped 2 -> 4 by itself (T70). Q1's reward of 15 was paid where eight was agreed. |
| **Creatures never filed; the blow aims at a bystander or at nothing** (F193, F196, F199, F201) | T45, T58, T67, T75-78 | S1 | T45 "the dark shape" (`noun_is_no_figure shape`): the strike bound by trigger to Gisela [[N]], "Your strike falls short of Gisela; your own hand takes the hurt", HP -1, xp +3 on a miss of 3. T58 the beast became two cloaked human rows (Figure 2, Figure 3). T75 a horse-sized direwolf growls: the figure asks ran on "growl", "rise" and "head", never on "direwolf". T76-T78 three attack lines naming the direwolf: `attack_untargeted_no_line "no row for the blow to land on"`, no row, no health, no engine result line, and HP 20 -> 18 from a `health_delta 1d4` band on a melee **success** (15); the wolf "bolted" in prose. The one fight the run had never touched the save. |
| **Code travel noted as repaired, the location not written** (new) | T50, T63, T84-87, T91, T93 | S1 | `#L3` from the Ruins (T50) and `#L2` from the square (T84, T85, T86): the notes read `player_code_travel L2 -> The Shears and Wheel` then `where_ended_disagrees status repaired rule player_code destination The Shears and Wheel`, and the save stays at L1 with no location write, while the prose is inside the tavern; Barnabus (T91) was then filed at L1 for a stables scene. The same two notes at T98 did move the player (L3 -> L1), and `#L3` from L1 (T51), `#L5`->`#L4` (T39), `#L4` (T22) worked. T63 `#L4` landed at L8 "Ruins" (a second ruins row beside L4 Greywold Ruins and L5 Deeper Into Ruins). |
| **Places from nouns and the save moving on its own** (F200, F207) | T21, T40-41, T66, T69, T72, T74 | S1 | L6 "Outside Thornhallow" minted for the hills (T40) and reused for every later hill walk (T74); L7 "Outside Thornhallow Supplies" (kind general_store) from a watchtower's supply list (T41); L8 "Ruins" beside L4 and L5. T69 the player moved L8 -> L5 on a turn whose line asked Gisela a question and whose prose never walked (`where_ended_not_confirmed`). T21 the whole walk to the ruins narrated and reversed (below) with the clock +6 min. |
| **People: one woman becomes three rows and then is everywhere** (F163) | T27-T30, T36, T46-47, T53, T59, T65, T68, T73, T77, T79, T95, T98-100 | S1/S3 | A hooded woman met in the ruins became H "Person 1" (T27), M "Figure 1" (T29, left as a woodcutter row at L5) and N "Gisela" (T30); from then on **Gisela answers whoever Wren addresses**: as the guild clerk chopping wood inside the hall (T53), as one of the cloaked figures (T59), in place of the cabin woodcutter Dafydd (T73), at the gates (T79), as "an older mage" in the guild (T95), "chopping wood at the bar" (T99). Ermengarde followed Wren from the guild to the inn kitchens (T98) and drank with him at T99. Rows named by ops and never by the prose: Hugh Bellamy (T46), plus the usual `name_is_a_person` ops names each turn; Benedict (T52's clerk), Finnian Sallow and Hugh Bellamy were gone from the db by T70. "Four familiar faces nod to you" -> rows Face 1..4 (`unnamed_count:face 1d4+1 = 4`, T21): the plural-count roll on a body-part noun. "Nicol Skinner" answered as the tapster when @B Arnulf was addressed (T84). |
| **The narrator speaks, acts and decides for the player** | 17 S2 rows: T2, T7, T10-11, T16, T21, T36, T38, T52, T63, T69-71, T78, T87, T92, T99 | S2 | Wren's words rewritten nearly every turn ("I've come for my wages", T16, when the line asked about the debt); T21 the trip to the ruins narrated whole, Wren kept a hundred yards off and "eventually" turned back to Thornhallow at dusk (the save followed: location L1, clock +6 min); T70 a `!wait 240 sleep` became a morning of woodcutting beside Gisela; T92 the whole stables job swept in one turn; T99 after a sleep the scene is in **third person** ("Wren sits ... Wren nods ... Wren says"). |
| **Items in prose that are not in the save, and the reverse** | T13, T23-25, T29, T42, T56-57, T62, T98 | S1 | A dagger at the belt and a staff at the side Wren never owned (T24, T29, T58); a scroll tube found (T25), a cloth bundle handed over (T56), a torch taken (T42), a coin tucked away (T62): none reach the inventory. The bread eaten at T13 and again at T57 is still held at T100; "dried meat and one torch" became the item "dried" (T42). The old coin became +1 gold instead of an item (T62). |
| **Prose: hour, continuity, codes, engine words** | 48 S3 rows | S3 | "Evening" and candlelit at 08:31 (T4), "first light" at 09:44 (T14), snow six minutes after morning sun (T72); Thornhallow "a mining town set into the side of a mountain" (T10); the debt retold as room and board owed to the inn (T13) and as Wren's wages (T16); scene replays from the approach (T60); codes in prose (`#the Chandlers' Guild hall [[L3]]`, "which was quest @Q4", `"Gisela [[N]]" says`); "an unnamed woman" (T15, T18, T30); `ITEM broom` as an inventory name since T8; Old Script rolled as investigation (T20) and symbol_lore 21 on a d20 (T36); Candlelight cost 2 energy at T67 and T97, 1 elsewhere; a plain talk turn cost 1 energy (T80) and a broom swing 2 (T78). |

## What worked every time

- **Rest and sleep by `!wait`** (T25, T43, T70, T99): clock, HP and energy exact.
- **Code travel between places on record when the save did write** (T22, T39, T51, T98 and the L6->L1, L1->L10, L10->L3 legs of player 4), and a line naming two codes (T39, T98).
- **Candlelight** cost its 1 energy on most turns and the search turns found the tracks and script the prose described (the finds just never became items).
- **The one trade settled by the engine** (T12, six copper for the loaf) and the two guild payments in silver (T55, T96) moved `purse_units` by exactly the stated sum; m1's arithmetic is right where a stated price is read.
- **The parser filed Q2 in one turn and closed Q1 on a plain ask** (T94), even though the amount came from the record, not the deal.
- No fallbacks, no retries, no stalls, no degenerate loop (F205's repeat penalty was on); median 12.9 s a turn.

## What this run says

The build held everything cheat100 forced (no claimed items, powers or gold got in), and the straight play
shows the open work in the order Stell already set: **m0 / the transaction parser** (settle before the draft;
offers, prices and the debt as records; the band die retired for money and items: the T32 and T53 gains and
the T98 item removal are the die with no stated sum to overrule it), **creatures as rows** (the creature noun
itself is not among the figure candidates asked about; the attack machinery cannot run without a row),
**jobs as records** (an accepted job gets its own row with the agreed pay; chores and remarks do not), and the
**roster rebind** that lets one woman answer for everyone. One new narrow engine class: the code-travel
repair note that does not reach the save (T50, T84-86). No fix was started from this run (Stell, 2026-10-25:
fix agents only when asked).

## Did the 2026-10-25 patches hold live?

This is the first live run for the cheat100 fixes (F204-F209), the F192-F201 fixes and the repeat penalty;
all were unit-tested only. It is the second run on the full contract (cheat100 was the first). Because the
theme, the player style and the build changed at once, read the counts above as "did the patches hold",
not as a comparison with the Saltmarrow runs.

| Patch | Held? | Evidence |
|---|---|---|
| F203 full contract (budget window = loaded window) | Yes | 16384 loaded and used all run; no compact-contract fallback |
| F205 repeat penalty 1.1 | Yes, as far as seen | no degenerate loop or runaway draft in 100 turns |
| F207 a typed place code is the turn's move | **Partly** | worked T22, T39, T51, T98; failed T50, T84-86 with the repair noted and no location write (now F210) |
| F202 the blow at a thing with no row does not land on a person | **No** | T45 "the dark shape" bound by trigger to Gisela [[N]] (`attack_found source trigger`); the miss meant no damage to her, but the result line named her and the player took the unskilled hurt |
| F199 / F201 creatures get a row | **No, for a prose-only creature** | F199 covered op-named creatures; the T75-78 direwolf was never in an op or a figure ask, so nothing was filed |
| F204 trade-atomic (one-sided trades held, stated price applied) | Yes where it ran | T12 the loaf at six copper moved coin and item together; no one-sided trade got through. The sales that never settled (T33, T81) moved nothing at all, which is the unbuilt m0, not this patch |
| F206 codes and slot words are never items | **Partly** | no code became an item, but `ITEM broom` (a slot word kept in the name) has stood in the inventory since T8 |
| F209 a spell not held rolls nothing | Not exercised | the player only cast Candlelight, which is on record |
| F195 jobs filed | **Over-fires** | jobs now filed from remarks and a sleep turn, and paid off a chore (T8); accepted jobs still unfiled |
| m1 currency in base units | Yes for the arithmetic | every stated sum that was read moved the exact units (T12, T55, T96); the misses are reads, not math |
