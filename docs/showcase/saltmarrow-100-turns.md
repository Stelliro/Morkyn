# Saltmarrow — 100-turn lore teaser

> **Backend: a high-end AI model.** Every model call in this run — the opening, each turn's draft, the verifier, the quest parser and the setup passes — was answered by **Claude** (Anthropic, `claude-opus-5-5`) through Mørkyn's cloud-API path, the same path a game pointed at Grok or OpenAI uses. Claude also played the player. A small OpenAI-compatible bridge ([tools/api_bridge_playtest.py](../../tools/api_bridge_playtest.py)) handed each request over and returned the answer. **The engine ran unchanged**: dice, skill checks, moves, items, quests, the ledger and every trim are Mørkyn's own. On a local 8B the prose will be plainer; the rules are the same.

## Run snapshot

| | |
| --- | --- |
| Turns played | **100** (plus the opening), no fallback turns |
| Model calls | **228**: 101 drafts, 85 verifier passes (14 revised), 39 quest-parser reads, 3 setup passes |
| In-game time | Day 1, 08:00 → Day 3, 18:26 (two Sleep-button nights, three waits) |
| Engine dice | **108** rolls: 82 skill checks, 26 band rolls (XP, gold, items, health, karma) |
| Places / people | 10 places · 19 people |
| Quests | 2 completed (Wat's cart, Keep the tide tower) · 1 surrendered (the customs bell, rung instead of sold) · 1 offered |
| Final state | Isk Tarrow at The Customs Tower · health 8/20 · XP 293 · gold 19 · level 1 (see issue #121) |
| Bugs found | **23 new issues (#100–#122)** and 10 older ones reopened — [findings](saltmarrow-findings.md), [issue log](../PLAYTEST_ISSUES.md) |

## Premise

Forty years ago the sea left Saltmarrow in one night and never came back. **Isk Tarrow** runs the exposed flats at dry tide, pulling salvage out of the drowned lower district before the water returns for a few hours each night. Her mother went out six years ago and never came home; the guild wrote her down as lost. This morning the reeve's clerk has chalked the tide two hours early, and the water in the channels is running the wrong way.

## Selected beats

### Turn 0 — Saltmarrow

> Morning in Saltmarrow smells of dried weed and lamp smoke. From the old harbour wall you can see what the sea left behind forty years ago: a grey plain of mud running out to the horizon, ribbed with channels, and the roofs of the lower district standing up out of it like teeth. Mooring rings hang on the wall above your head, rusted open, waiting for boats that stopped coming before you were born.
>
> A crowd of runners has already gathered at the guild's tally board, where a clerk in an ink-stained apron is nailing up the day's contracts. One sheet is pinned higher than the rest and carries the guild's red thumbprint: the bell of the old customs house, wanted whole, paid in coin rather than credit. Two runners read it, laugh, and walk away. The customs house sits furthest out on the flats. …

*Engine:* system: Initialization phase pending: on the first model turn, establish base play assumptions, respect immutable ability base descriptions, · Verifier replaced narration. · rumor: Philippa Kemp's nephew Tam went out on the flats at the last dry tide with a hand cart and has not come back. · fact: The guild posted a coin-paid contract for the bell of the old customs house, furthest out on the flats.

### Turn 3 — Saltmarrow

**Player:** I flip open my mother's tide-reckoner, set it against the two chalk marks, and use Tidecount to feel for how long until the water comes back.

> The tide-reckoner opens with a click that is louder than it should be. Its brass face is scratched with channel names in your mother's small hand, and the needle settles, shivers, and settles again. You hold it up beside the chalk until both marks sit behind the glass.
>
> Then you stop looking and let Tidecount do the reading. It comes the way it always comes, as a slow pressure along the jaw, like biting down on something cold. The flats are empty now; you can feel that much as plainly as the stone under your boots. But the water is not far. It is sitting out past the furthest channels, close, and it is coming back in a little under four hours. Not at the old mark. Not at Jessop's new one either. Sooner than both.
>
> And it is not coming evenly. The far channels fill first, out where the customs house stands, then the water runs back toward the wall along the deep cuts. …

*Engine:* Verifier replaced narration. · fact: Tidecount: the water returns a little under four hours after 08:18, sooner than both tide marks; the far channels by the customs house · check: You rolled 3 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (failure)  ·  margin -6

### Turn 11 — The Deep Channel

**Player:** I keep walking out along the channel and watch the mud on both banks for hand-cart wheel tracks.

> You walk slowly enough to read the banks. The mud on either side of the channel is a record of everything that crossed it since the last water: bird feet, the long smears where runners slid down, the deep twin holes of someone who stood still too long and had to pull out.
>
> Most of it is boots. Then, a quarter of a mile out, you find what you were looking for. Two narrow wheel ruts, a hand's width apart, come down the left bank at a slant, cross the channel floor, and climb out again on the right. The edges are still sharp. Whoever pushed that cart came through after the last water went out, not before.
>
> They do not go on toward the customs house. On the right bank the ruts turn away from the tower and run straight for the drowned rows of the lower district, between two roofs that stand up out of the mud like a gate. …

*Engine:* system: Travel action with no MOVE op and no resolvable destination; player stayed put. · quest: A hand cart crossed the deep channel after the last water and turned toward the lower district, not the customs house; a small worn b · check: You rolled 18 with your base of 10 (wisdom) and a modifier of +0 (attr +0 + skill +0 (untr | Result: success (success)  ·  margin +8

### Turn 24 — The Old Fish Market

**Player:** I stop under the eaves to let my eyes get used to the dark, then call in: "Tam? Tam Kemp? Your aunt sent me."

> The dark under the eaves thins slowly. A long hall comes out of it: stone counters in rows, iron hooks hanging from the beams, and a floor of planks laid over whatever was underneath, black and furred with old weed. The cart ruts run in across the mud at the door and stop where the planks begin.
>
> Halfway down the hall there is a hole in the floor. A ragged one, the shape of a cart turned on its side, with snapped boards pointing down into it.
>
> Your voice goes down the hall and comes back to you off the stone. Then, from the hole, small and cracked:
>
> "Here! I'm here, I'm down here!" A scrabbling, and a gasp. "Don't come on the boards. Don't, they go. They just go."
>
> A pale hand shows for a moment at the broken edge, catching at a plank end, and drops back.
>
> "I can't get my leg out. The cart's on it." The voice is very young and trying hard not to be. "There's water coming up. …

### Turn 30 — The Chimney Roof

**Player:** I sit down with my back to the chimney beside Tam, get my breath, and use Tidecount on that white line.

> The chimney stones are warm against your back. Tam Kemp is a hunched shape at your shoulder, still not speaking. You close your eyes and let Tidecount come, and for once it does not come gently.
>
> It hits like cold water in a bad tooth. The white line is the sea. Not the tide that comes back up the channels every night and goes out again, but the sea itself, the whole grey weight of it, standing up along the horizon where it has not stood in forty years. It is coming in over the outer flats the way water comes into a footprint: all at once and from every side.
>
> And it is coming early. You were right at the wall and right in the channel, but you were not right enough. Not an hour now. Less. The far channels are already full; the deep channel is filling; the rows will be next, and the water will not stop at the first-floor windows tonight.
>
> You open your eyes. …

### Turn 32 — The Chimney Roof

**Player:** I wind the rope loop tighter round my fist, hook my other arm round the chimney stack, and hold on.

> You wind the loop until the wet hemp bites into the back of your hand, hook your other arm round the chimney stack, and hold.
>
> It comes down the rows like a cart down a hill. First the roar, then a wind that smells of salt and weed and something older, a cold, green, deep smell that has not been on the flats in forty years. Then the water itself: a brown wall no higher than a man, shoving a scum of foam and timber ahead of it, pouring into the street below you between the drowned houses and climbing them as if they were steps.
>
> It reaches the first-floor windows in the time it takes to breathe twice. It reaches the rubble slope you climbed and swallows it. Spray comes over the gutter and across the tiles, and for a moment the whole roof is white and you cannot see Tam Kemp at all, only feel the rope jerk taut in your fist. …

*Engine:* dice: damage (trivial): 1 +1 = 1, lost (-1) · dice: player.health_delta band trivial -> -1

### Turn 45 — The Customs Tower

**Player:** I go up the last of the stair, slow and quiet, toward that step. "Mam?"

> The stair narrows as it climbs, until your shoulders brush stone on both sides, and then it opens out under the sky.
>
> This is the top of the tower, what is left of the bell-chamber: four stone arches open to the wind, the roof long gone, rain blowing straight through. In the middle a great oak frame stands empty, its iron bearings rusted bright orange. The bell is not in it. The bell is on the floor, on its side in a nest of rope and timber rollers, as if someone has been trying, a little at a time, to move something no one person could move.
>
> There is a woman beside it.
>
> She is thin, burnt dark by wind, barefoot, in a runner's oilskin patched so many times it is more patch than skin. Grey hair cut short with a knife. She has a mallet in one hand and an iron wedge in the other, and she has stopped dead with both raised, looking at you. Her jaw is your jaw.
>
> She does not say anything. …

*Engine:* Verifier replaced npcs. · system: Travel action with no MOVE op and no resolvable destination; player stayed put. · quest: Step done: Raise the customs-house bell (Reach the old customs house) · check: You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +4

### Turn 48 — The Customs Tower

**Player:** I take Mara's hand off her chest and hold it. "You don't have to talk. Show me. Is the bell why you stayed?"

> Mara Tarrow looks down at your hand round hers for a long moment. Then she nods, once, hard, and pulls you by it across the bell-chamber to a beam by the stair-head where a stub of charcoal hangs on a string.
>
> The beam is covered in writing. Tally marks, dates, channel names, all the way along it, years of them, and under them a clear space she must have kept for something. She takes the charcoal and writes in it, in big plain capitals, pressing so hard the stick snaps halfway through and she goes on with the stub.
>
> REEVE PAID ME TO WATCH THE SEA. SECRET. H. CAME EACH MONTH. TOOK MY FIGURES. BROUGHT FOOD.
>
> She stops, breathing hard, and writes again underneath.
>
> I TOLD THEM IT WAS COMING. HE SAID HE WOULD WARN THE TOWN. HE NEVER DID. …

*Engine:* fact: The reeve secretly paid Mara Tarrow to watch the sea from the customs tower; Hereward Jessop fetched her figures monthly. She warned t · check: You rolled 9 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: success (barely)  ·  margin +2

### Turn 55 — The Customs Tower

**Player:** I take the bell rope Mam has tied to the clapper and ring it. Hard. Again and again, toward Saltmarrow.

> Mara Tarrow has knotted a length of her old grey line to the clapper's ring, and it hangs down beside the frame to the height of your hand. You take it.
>
> The first stroke is nothing. The clapper swings, heavy and slow, and kisses the bronze, and a dull wooden sound comes out like a fist on a door. On the third stroke the bell wakes.
>
> It is not a sound so much as a weight. It comes out of the bronze and fills the bell-chamber and goes on through the stone into your feet, into your teeth, into the old ache of Tidecount along your jaw. It goes out through the four arches over the water in every direction at once, and the water carries it. Again. Again. You lean your whole body on the rope and the bell swings up and rolls over and speaks, and each stroke goes out over the drowned flats toward the low dark line of Saltmarrow's roofs.
>
> Tam Kemp has stood up. …

*Engine:* Dropped 2 sentence(s) or clause(s) where the narration acted, thought or decided for the player. · dice: xp (large): 3d8+16 [4, 3, 7] +16 = 30 · event: Isk rang the customs bell from the tower; Saltmarrow heard and answered with its temple bell. · check: You rolled 19 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +10

### Turn 64 — Saltmarrow

**Player:** I turn round to the stair. "Hereward Jessop. You carried her figures every month. Tell them."

> Hereward Jessop is still at the top of the stairs with his hat crushed in his hands. Every face on the wall turns to him. You watch him understand what you are asking, and what it will cost, and you watch him decide.
>
> He climbs onto the stone bench by the tally board where he has stood every morning for six years to chalk the tides, and he faces the crowd.
>
> "She's telling you true." His clerk's voice is thin, but the wall is so quiet it carries. "That's Mara Tarrow. She didn't drown. The reeve found her on the outer bar six years ago, half dead, and he put her in the customs tower and paid her to watch the sea, because she said it was coming back and he believed her." He wets his lips. "Every month I rowed out at dry tide with her food and came back with her figures, and every month the reeve read them and locked them in his chest. …

*Engine:* event: Hereward Jessop publicly confessed that the reeve hid Mara Tarrow's warnings and chalked false tides.

### Turn 69 — Saltmarrow

**Player:** I hand Mam the charcoal from behind her ear. "Tell them yourself, Mam. On the board."

> It is Baldwin Thorne who answers you, quickly, kindly, stepping half between you and the board.
>
> "Now, now. Let the poor woman be." He spreads his soft hands. "You can see the state of her. Six years alone on the bar. She doesn't know what day it is, let alone what she's writing. Mara, my dear, give the girl back her charcoal and come along home with me, and we'll get you warm."
>
> Mara Tarrow looks at him. Then she steps round him as if he were a post on the wall, and goes to the tally board, to the one clear stretch of plank at the bottom where nothing is pinned, and writes.
>
> She writes big, so the back of the crowd can read it. The charcoal squeals on the wet wood.
>
> I KNEW THE DAY. I WROTE IT DOWN. HE READ IT. HE SAID WAIT.
>
> She stops. Her hand is shaking. Then she writes one more line under it, smaller, and steps back so everyone can see.
>
> MY NAME IS MARA TARROW. I AM NOT MAD. …

*Engine:* system: Travel action with no MOVE op and no resolvable destination; player stayed put. · check: You rolled 11 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +3

### Turn 85 — Saltmarrow

**Player:** With the hands Hereward found, we lift the drained cart up the stairs and wheel it along the wall to the chandlery door. I give Philippa back her line and the cart-hooks. "Wat's cart. Whole."

> With eight pairs of hands the drained cart is nothing. The cooper takes one shaft. People step out of the way. Somebody claps, and stops, embarrassed.
>
> You stop it at the chandlery door. Philippa comes out wiping her hands, and sees what it is, and stands very still. She puts one hand flat on the side of the bed, over the carved W, the way Mara put her hand on the reckoner.
>
> You lift Philippa's coil of line off your shoulder and the cart-hooks off your belt and hold them out. She takes them without looking at them. Then she goes back inside and comes out with fifteen coins in a twist of oilcloth, and presses them into your hand, and closes your fingers over them with both of hers, hard.
>
> Hereward Jessop is already backing away into the crowd, uncomfortable with the thanks that are not even his.
>
> "It was the town did that, not me," he says, too quickly, when you look at him. …

*Engine:* Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player. · quest: Quest complete: Bring up Wat's cart (from Philippa Kemp): +15 gold, +75 XP · dice: item_count (small): 1 +1 = 1 · item_count (small): 1 +1 = 1 · check: You rolled 5 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin

### Turn 91 — Saltmarrow

**Player:** I strike the flint over the wick until it catches, and light the lamp. "One more time. For nobody lost."

> The flint is old and the steel is rusty and the wind off the land keeps finding the gap in your cupped hands. You strike, and strike, and on the sixth strike a spark lands in the tinder and glows, and you breathe on it the way your mother taught you when you were small, and it takes.
>
> You put the tiny flame to the candle stub in the old ship's lantern. It gutters. It holds. A small yellow light stands up inside the smoked glass in the grey morning, absurd and brave, over the slack sea between the drowned roofs.
>
> Nobody needs it. That is the point.
>
> Mara Tarrow closes the lantern's little door very gently, as if it were a cupboard in a sleeping child's room. Jocosa Kettle has the folded red cloth in her fist and her face still turned away to the open water, and her shoulders are shaking, and she is not making a sound. …

*Engine:* mechanics: Deterministic combat: unarmed vs B Hereward Jessop resolved as hit; damage 3; health 21->18/21. · dice: xp (small): 1d6+2 [2] +2 = 4 · check: You rolled 14 with your base of 10 (strength) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +5 · dice: player.xp_delta band small -> 4

### Turn 98 — The Customs Tower

**Player:** At 18.20 by Mam's beam, I put her hand on the bell rope beside mine, and we ring the high water for Saltmarrow together.

> At twenty past six by the beam, the sea stops breathing in.
>
> The bell wakes slowly, the way it did the first time, a dull knock and then a deeper one, and then it rolls over in its frame and speaks. The sound goes out of the four arches over the high still water, over the drowned rows and the burnt-out lamp and the slack sea, all the way to the wall. You ring it slow and even, the way a high water should be rung, not the frantic warning of two days ago but a plain steady telling. Here is the top of the tide. Here is the hour. You can trust it.
>
> Across the water, small and clear, a lantern goes up on the harbour wall by the tally board. Then another. Then the whole wall, lantern after lantern, answering.
>
> You let the rope go. The last stroke hums on in the bronze.
>
> Beside you, Mara Tarrow is still holding the rope. …

*Engine:* Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player. · quest: Quest complete: Keep the tide tower (from Una Rendle): +4 gold, +50 XP · dice: xp (large): 3d8+16 [6, 3, 5] +16 = 30 · check: You rolled 18 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (un | Result: success (success)  ·  margin +6

### Turn 100 — The Customs Tower

**Player:** I take a fresh stick of charcoal from Mam's box and, under her NOT YET, write my first line on the beam: today's date, high water 18.20, rung, answered.

> The box of charcoal sticks sits on the door-table by the brass machine. You take a fresh one. It is light and dry and leaves black on your fingers, the way your mother's fingers have been black for six years.
>
> Under NOT YET, in the clear stretch of the beam, you write. Your hand is not as small and careful as hers. The letters come out bigger and rougher, a runner's hand. Today's date. High water 18.20. Rung. Answered.
>
> It is the first line on the beam in any hand but hers.
>
> Mara Tarrow does not turn round. She stands in the seaward arch with her back to you and her arms wrapped round herself, as still as the oak frame, and whatever she is feeling she is keeping it out there with the sea, where you cannot see it. The silence between you is hard as a shut door. She has had six years of her own company and she is not giving it up for a daughter in three days, not tonight. …

*Engine:* Dropped 1 sentence(s) or clause(s) where the narration acted, thought or decided for the player. · dice: xp (small): 1d6+2 [1] +2 = 3 · fact: Day three, 18.20: the first high water rung by the tide-readers Mara and Isk Tarrow; Isk's first line written on the beam. · check: You rolled 2 with your base of 10 (charisma) and a modifier of +0 (attr +0 + skill +0 (unt | Result: failure (bad nothing)  ·  margin

## What the engine decided

The model wrote the words. These were Mørkyn's, not the model's:

- **Every number.** 108 server rolls, seeded and logged in `dice_rolls`; the model only named bands. The climb that failed at the 'easy' ramp was a natural 1 rolled by the engine (turn 13), and the injury, −6 health and a lasting limp, was the engine's rule.
- **Who answers.** Each turn the engine picked the addressee and only that person could speak. When it picked wrong (issue #104), the story had to work round it, and you can see the seams in the transcript.
- **What you own.** The rope bought in turn 8 was refused because the wording did not read as a purchase; bought again in turn 9 with plain words, it was granted, and the purse dropped by exactly three.
- **What happened to quests.** The guild's bell contract was surrendered in the ledger; Wat's cart paid fifteen coin and 75 XP when it reached the chandlery; the tide-tower post paid on the first high water rung.
- **Time and the body.** Energy ran out on day one and blocked the climb until the player slept; two nights of sleep came from the Wait/Sleep button, with the engine's own random events (a pickpocket, crowd noise) for the model to narrate.

## Honest notes

- The prose is Claude's, not a local model's. This shows what Mørkyn's engine does with a strong writer behind it, and the [transcript](saltmarrow-transcript.md) shows every place the engine changed that writing — including cuts that were wrong.
- The run was also a bug hunt: the GM followed each call's packet strictly, so engine mistakes show up in the story rather than being smoothed over. They are logged as #100–#122.
- Because the GM also verified its own drafts, it caught and corrected its own slips (invented player speech, an NPC knowing a name it was never told) — 14 verifier revisions in all.

## Data

- Full transcript: [saltmarrow-transcript.md](saltmarrow-transcript.md)
- Metrics: [saltmarrow-metrics.json](saltmarrow-metrics.json)
- World database at the end, read-only export: [saltmarrow-db/final.md](saltmarrow-db/final.md) (readable) · [saltmarrow-db/final.json](saltmarrow-db/final.json) (every table and row) · also the start ([turn-000.md](saltmarrow-db/turn-000.md)) and the midpoint ([turn-050.md](saltmarrow-db/turn-050.md)). Made with [tools/export_world_db.py](../../tools/export_world_db.py).
- Setup used: [saltmarrow-setup.json](saltmarrow-setup.json)
- Findings by root cause: [saltmarrow-findings.md](saltmarrow-findings.md)

The earlier engine-only stress run (templated player and GM, no model) is kept at [100-turn-lore-teaser.md](100-turn-lore-teaser.md).
