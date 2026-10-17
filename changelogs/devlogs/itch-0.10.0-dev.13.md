<!-- Markdown copy of the itch.io devlog "0.10 dev builds: the save follows the story". The HTML original is posted at https://stelliro.itch.io/morkyn -->

# 0.10 Dev Builds, Part Three

184 test runs. 377 fixes. The save follows the story.

## Since The Last Post

The last devlog ended at dev.9. Since then dev.10, dev.11 and dev.12 went out, and dev.13 lands with this post.

dev.11 brought **Saltmarrow**, a 100-turn lore teaser: a drowned harbour town, a debt to the salvage guild, and a tide that will not wait. Claude played both sides, player and narrator, and every fault went into the public issue log, now 145 entries long.

Then we replayed Saltmarrow with a local model as the narrator, the way you would play it at home. An agent typed the player's lines. The game ran exactly as it ships.

> One question for every turn: does the save still agree with the story?

## How The Testing Works

- **Every turn leaves a trace**: what the model wrote, every change to the save with the line of code that made it, every refusal, and how long each step took.

- **A run stops at the first fault in the save**: a person in the wrong place, gold that moved for no reason, a job no one offered.

- **Each fault is fixed by its class, not its wording.** "The prose names a place it only walks past" is one fix, not one rule per sentence. Each fix gets a test, the whole suite of about 3,500 tests runs, and a new run starts.

- **You can watch.** A test run serves a read-only view of the game that updates after every turn.

There were 43 runs on Qwen2.5 7B, then 141 on Qwen3 8B, the model we are aiming for.

## What A Fault Looks Like

Small ones, mostly. Each of these broke the save in a real run:

- "You step past the Collapsed Market Stall and into the salvage yard" put you inside the stall.

- The narrator wrote a line for you, *You say, "I need to speak with the tallyman about work to pay my debt,"* and that line was filed as the tallyman's job offer.

- "A desk cluttered with ledgers and loose coins" paid you 10 gold.

- The tallyman you walked in to see stayed behind in the street, because the prose called him only "a man behind the counter". The next turn sat a stranger at his desk.

- Two jobs both called "Salvage Job", from two different people, were read as one job, so the second was never recorded.

## What Changed

- **Places.** A place you reach, a place you pass and a place someone only mentions are told apart. A dock the tallyman names becomes part of the town when you first walk there. A move the model replaced leaves no empty building behind.

- **People.** People stand where the prose shows them, and the one you came to talk to comes along when you walk in. They keep their names and jobs, and a name the narrator picks has to fit the person it describes. "Tallyman" is a job, not a name, and your own name is never given to anyone else.

- **Jobs.** A job is filed when someone offers a real task, and only once per offer, under the person who offered it. "You'll have to prove yourself" or "the guild has work" sets no task yet. Saying "I'll take that one" takes it; a hedge does not.

- **Gold and items.** Coin moves when it changes hands in the scene, not when someone is willing to pay or coins lie on a table. A thing handed to you under another word ("the slip") is the item you were given.

- **Your words.** Lines the narrator gives you, acceptances you never typed, and your own line retold back at you are removed. Your typed words are never cut.

## From The Saltmarrow Run

- **Levels rise with XP.** The first run ended at 293 XP and still level 1.

- **Sleep heals.**

- **A sum the prose names is the sum that moves.** "Nine coins. All you had." takes nine.

- **Checks read only your own line.** Talking to someone no longer rolls persuasion on every turn, and your opponent is the person you are dealing with.

- **People you take along move with you**: "Tam and I go", "with Tam", "I carry Tam up the ladder".

## Still Rough

- **No clean 100-turn run yet.** The 8B runs still turn up about one new save fault each, within the first seven turns.

- **The narrator still writes your inner life**: "your heart pounding", "You had been here before". A rule cannot tell these from real backstory, so these are logged rather than cut until we settle on a better approach.

- **Speed.** On a 12 GB card the 8B took a median of 25.5 seconds per turn over the last 58 measured turns, with most between 16 and 43.

## Next

The job reader has had the most fixes of anything in these runs: it reads a whole turn and decides the offer, the person, the steps, whether you took it and whether it is a repeat, all in one go. The lesson from this round is that when the model keeps failing a task, the task is too big. So it is being split into smaller questions, with the game deciding the rest.

Then: a 100-turn run on the 8B with no faults, the same on the 7B, then a stable **0.10.0**, then **1.0** as a standalone download with starter saves.

## Versions

**0.10.0-dev.10** to **0.10.0-dev.13** are tagged on GitHub.

Changelog: [CHANGELOG.md](https://github.com/Stelliro/Morkyn/blob/main/CHANGELOG.md)  
Issue log: [docs/PLAYTEST_ISSUES.md](https://github.com/Stelliro/Morkyn/blob/main/docs/PLAYTEST_ISSUES.md)  
8B test findings: [docs/showcase/saltmarrow-8b-findings.md](https://github.com/Stelliro/Morkyn/blob/main/docs/showcase/saltmarrow-8b-findings.md)  
Source: [github.com/Stelliro/Morkyn](https://github.com/Stelliro/Morkyn)
