<!-- Markdown copy of the itch.io devlog "0.10 dev builds: the narrator stops playing your character". The HTML original is posted at https://stelliro.itch.io/morkyn -->

# 0.10 Dev Builds

The narrator stops playing your character. The towns get streets.

## Where This Comes From

0.10 began as a pile of systems. Then it got played. A first game ended four turns in: the narrator forgot a pursuit mid-chase, made a baker run someone else's shop, handed out two loaves of bread nobody gave, and put the player's own threat in an NPC's mouth.

Every one of those went into a public issue log with the turn, the trace, and the cause. Then the same scripted games were played again on a local 8B model, scored blind, and played again after each fix. Sixty-two issues so far. This is what came out of it.

> Same rule as before, applied harder: the model can propose a change. The game decides what is true.

## Your Character Is Yours

- The narration no longer nods, decides, pockets things, or speaks for you. Your words stay yours in every stage, and a sentence where "you" does something you never asked for is removed.

- Items reach your pack when someone hands them over, you buy them, or you said you take them. Touching a loaf is not owning it. A tart you taste and hand back is not a gain.

- The engine decides who you are talking to: a tag, a name in your line, "everyone", or whoever was just revealed or spoke last. A **Talking to** chip above the input shows it, and you can change it.

- The scene remembers what you are in the middle of. A pursuit, the quest step you accepted, and who came along survive a side action. Following someone moves you with them.

## Towns You Can Walk

Every town cell already held a 128 by 128 grid. It was empty. Now it is generated the first time you get there: avenues, main roads, side streets and alleys that join across the whole city, and building plots along them.

- Each roadside plot rolls for a shop by its ward. Market streets are mostly shops. Residential streets get the odd corner store. Temple and government wards almost none.

- The map zooms from the world to the city to the streets. Click a plot to walk there, or type "go to the bakery". You follow the roads and the clock moves.

- The narrator is handed the real shops near you each turn. A shop becomes a place with a keeper the first time you walk in. A bakery the model invents gets pointed at the real one.

- The day and time sit in the Scene header. Shops keep their hours.

First version. The street view is small in the side panel, and the prose can still wander past the door the engine stopped you at. Both are logged.

## Faster, Plainer Prose

The second model that rewrote each draft paragraph by paragraph was tested against the draft alone, on the same games, scored blind. It doubled the turn time and was the source of most repeated lines. It is now off by default and stays a launcher toggle.

- Restated sentences across a test game: **10 down to 1**.

- The narrator acting for you: **7 down to 4**, and falling.

- Turns on Qwen3 8B (Q4) on a 12 GB card: most between **5 and 35 seconds**, against about 32 seconds with the old writer.

- Every NPC you addressed answered in their own voice.

The launcher's automatic context size now fits the free memory on your card instead of filling it. On a 12 GB card it settles at 24,576 tokens and no longer hangs.

## A World That Agrees With Itself

- **Fresh names.** Two test games in a row opened with the same baker named Aria, because one example sat in a prompt. Names, jobs and shop names now come from large pools filtered by world, drawn fresh each call, and never reused in the same world.

- **A character that adds up.** Name, sex and pronouns, where the backstory says you arrive and where you start, what you wear and what is in the gear slots, and what the backstory says you carry are checked against each other at setup.

- **Starting gear with stats.** One card per item with a slot, a description, rolled weight, durability, protection and value, and stat bonuses. Feet, torso and legs are always filled, named for your world.

- **World facts as small rows.** Races, factions, customs and rules become short linked records, and each turn reads only the ones that matter. Custom proficiencies become real skills with a start rank, how they grow, and a limit.

- **Shops and people stay put.** Walking into a shop makes it a place with one keeper. Tradespeople have workplaces, so a baker in someone else's shop is a visitor. "Come along" adds them to your party.

- **Quests are checked.** The narrator offers work. A second pass confirms the offer and the engine logs it.

- **A map someone gives you** reveals ground on your map instead of taking a pack slot.

## Still Rough

The biggest open problem has a name in the log: the prose and the save disagree. The narration walks into a bakery the engine never made, or the engine makes a forge the narration never shows. Towns cut this down by giving the narrator the real list of shops. The next step is one check that reads the finished scene against the turn's changes and makes them agree before the turn ships.

Also known: a shop can be stored twice when the story named it before you walked in, a market street can hold four general stores, and the automatic context can drop too low if another program is holding the GPU.

## Versions

0.10 now ships as numbered dev builds, **0.10.0-dev.1** to **0.10.0-dev.6**, each tagged on GitHub with its own changelog section, so you can see what changed between the copy you have and the one the launcher offers.

Next: the prose-and-save check, town polish, a stable **0.10.0**, then **1.0** as a standalone download with a set of starter saves.

Changelog: [CHANGELOG.md](https://github.com/Stelliro/Morkyn/blob/main/CHANGELOG.md)  
Issue log: [docs/PLAYTEST_ISSUES.md](https://github.com/Stelliro/Morkyn/blob/main/docs/PLAYTEST_ISSUES.md)  
Source: [github.com/Stelliro/Morkyn](https://github.com/Stelliro/Morkyn)
