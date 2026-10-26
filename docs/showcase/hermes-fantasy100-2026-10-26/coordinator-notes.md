# Coordinator notes: fantasy100 (Hermes 3 8B, Thornhallow, 2026-10-26)

Build 084c3f0 (= dee4eed + the setup file). Context 16384 (full contract). Four Sonnet players, 25 turns each.
The players' worst claims, checked against `turns/NNN.json` (engine.delta, engine.notes, dice).

## Player 1 (T1-T25)

- **T8 purse 12 -> 27 with no pay shown.** Confirmed. The quest parser filed `#3 Floor-cleaning` from the
  sweeping line, with a step "clean the floor", and paid it in the same turn (delta gold writes [15, 55];
  note `model_reward_dropped ... the quest parser finishes and pays this job`). The prose has Roger praising
  the work and offering more; no coin. A -7 band die was voided (`loss_not_shown`). Class: job filed and paid
  off a chore the player never asked pay for (F156/F195 family, now over-firing rather than under).
- **T11 purse 27 -> 16 on a question about a loaf for three copper.** Confirmed. `player.gold_delta 2d6+3 = -11`
  (turn_bands) was settled as the spend (`gold_shadow ... engine settled -11, final -11, source null`) because the
  interpreter said money was leaving (`out: true`): the player did commit to buy, but the prose only quotes a
  counter-price of six copper and nothing is paid. The die's amount, not the prose's, moved the purse: F188
  (money from the die) is alive on the full contract. Also `agreed_price_set Q3 from 15 to 0.0003` (three
  copper in gold).
- **T19 "one silver coin ... as a payment on the debt": purse stayed 15.** Confirmed. `payment_unpriced_banded
  -small` then `spend_voided`: the engine did not read "one silver coin" as a stated amount, the interpreter
  said no money left, and the band was voided. The prose shows the coin handed over. A stated denomination
  the m1 readers should catch (one silver = 100 units) was missed; the debt itself is not on record anywhere.
- **T21 the walk to the ruins narrated whole, ending back in Thornhallow at dusk.** Confirmed as agency (S2):
  the prose decided the player kept a hundred yards off, waited out the morning and turned back; the save
  followed the prose (location -> Thornhallow, clock +6 min only). `Greywold Ruins` (#4) was filed as a place
  and `Ruins Exploration` as an event. Four rows `Face 1..4` were filed from "four familiar faces"
  (`noun_is_a_figure kind=face`, count 1d4+1 = 4): the plural-count mechanism firing on a body-part noun.
- Player 1 reports no fallbacks and no turn over 60 s (max 31.8 s at T11).

## Player 2 (T26-T50)

- **T32 purse 15 -> 27 on offering to sell the loaf for four copper.** Confirmed. `player.gold_delta 2d6+3 = +12`
  (turn_bands) was applied (`gold_shadow ... interpreter out false in false; engine settled 12, final 12, source
  null`). The prose has Gisela countering at six copper; nothing changes hands. The void step only voids a
  *loss* the interpreter does not confirm (`_void_unbought_spend`); an unconfirmed band *gain* goes through.
  F188's gain side, alive on the full contract.
- **T45 the strike at "the dark shape" fell on Gisela [[N]].** Confirmed. The shape was judged no figure
  (`noun_is_no_figure kind=shape`), so no creature row existed; the attack check bound by trigger to N
  (`attack_found target N source trigger`), the melee 3 was a miss (`combat_follows_attack_check ... now miss`),
  the engine's line "Your strike falls short of Gisela [[N]]; your own hand takes the hurt" was not in the prose
  (`attack_not_in_prose`), HP 20 -> 19 by the unskilled rule and xp +3 from a band die on a miss. The prose
  itself has the figure vanish and the blow hit nothing. Blow at a bystander with no creature on record:
  F196/F201 family (the shape was never a row to aim at).
- **T48 Gisela upends a pouch of gold into the player's palm; purse stays 27.** Confirmed.
  `gain_without_coin_dropped stated 15, why: the prose shows no coin reaching the player` while the prose reads
  "A handful of gold coins spill onto your palm ... 'Take what you deserve'". The interpreter said `in: true`;
  the stated-gold reader overruled it. Q4 was not completed either (the `@Q4` reference in the line did not
  close the job). T49 "I count the coins ... fifteen of them": no gain, a -small payment band voided instead.
  F156 family (a payout shown in prose, refused by the reader).
- **T50 `#L3` (the guild hall) from the Ruins ended at L1 Thornhallow.** Confirmed as a mismatch between the
  note and the save: `player_code_travel L3 -> the Chandlers' Guild hall`, `where_ended_disagrees status
  repaired rule player_code destination the Chandlers' Guild hall`, yet `location Ruins (L8) -> Thornhallow
  (L1)`. The prose has "a good mile or more to go", so landing short is defensible; the note claiming the
  repair went to L3 is not what was written.
- Player 2 reports no fallbacks, max turn 19 s.

## Player 3 (T51-T75)

- **T53 "I offer the clerk 10 silver toward the debt": purse 27 -> 40.** Confirmed. The interpreter answered
  both `out: true` and `in: true`, the stated-gold readers found nothing (`paid [] received []`), and the band
  die `2d6+3 = +13` was applied as the settlement (`engine settled 13, final 13, source null`). A payment of
  10 silver (1,000 units) became a gain of 13 gold (130,000 units). F188 again, with the interpreter's two
  answers contradicting each other and no tie-break.
- **T55 "I count five silver onto the counter": purse_units 409994 -> 409494, gold 40 -> 40.** Correct in the
  save: `prose_paid -0.05 gold, money_delta -500`. The `gold` field is the integer mirror and cannot show half
  a silver; this is the mirror Stell's money decision already marks for retirement, not a new fault. The debt
  itself still has no record, so nothing was reduced; the clerks quote a different figure each visit.
- **T70 `!wait 240 sleep` narrated a morning of woodcutting and filed Q6 "cut firewood".** Confirmed. The sleep
  applied correctly (energy 6 -> 15, HP 19 -> 20) but the prose had the player work the morning with Gisela and
  the parser kept the offer (`checked_offer_kept ... no_offer_in_exchange`) and filed `#6 cut firewood` with a
  step. Agency on a wait turn (S2) and a job filed from chatter (F195 over-firing).
- **T75 the direwolf growls; no row.** Confirmed. The figure asks ran on the nouns "growl", "rise" and "head"
  (`noun_is_no_figure` x3) and never on "direwolf"; no creature row, no encounter. The perception 20 found the
  tracks. F193/F199 family: the creature noun itself was not among the candidates asked about.
- Player 3 reports no fallbacks, max turn 25 s.

## Player 4 (T76-T100)

- **T76-T78 "I swing my broom at the direwolf's snout": no row, no result line.** Confirmed.
  `attack_untargeted_no_line outcome success noun direwolf why: no row for the blow to land on`; the figure ask
  that turn ran on "human" only. The melee 15 was a success and still HP 20 -> 18 from a `player.health_delta 1d4`
  band die. A creature present in the prose for four turns (T75-T78) and named by the player in three attack
  lines was never filed, so the attack machinery had nothing to hit. F193/F199 family, prose-only creature.
- **T81 "two silver, Roger, and it is yours": Roger agrees and pockets the meat; nothing moves.** Confirmed.
  Interpreter `out false, in false`, readers empty, delta empty: the meat stays in the inventory, the purse stays
  41. A completed sale in the prose with no settlement (F194 family; the settle-before-the-draft design is
  not built).
- **T84 `#L2` ended at L1.** Confirmed, and the same shape as T50: `player_code_travel L2 -> The Shears and
  Wheel`, `where_ended_disagrees status repaired rule player_code destination The Shears and Wheel`, yet the
  save has no location write and stays Thornhallow; the prose is inside the tavern. T98 carries the same two
  notes and the location did move (L3 -> L1). So the "repaired" note does not always reach the save: a new,
  narrow engine class (code travel noted as repaired, location not written), seen twice (T50, T84).
- **T94 "please pay me the eight gold we agreed": purse 41 -> 56.** Confirmed. The parser paid Q1's recorded
  reward (`paid Q1 step_done +15 gold +25 XP source parser`), not the eight gold the prose shows Edith counting
  out; the stated eight was read as a *loss* (`stated_mention -8`, voided as `loss_not_shown`). Payout by
  record over the agreed amount, and the stated amount's direction read backwards (F156 cont.).
- **T98 "I will sell him the dried meat tomorrow": the meat left the inventory.** Confirmed. `item:dried 1`
  (turn_bands) removed it (`inventory dried 1 -> 0`); no coin received; the prose only has Roger nodding at the
  promise. An item moved by the band die on a promise (F188's item sibling).
- Player 4 reports no fallbacks, max turn 31 s.
