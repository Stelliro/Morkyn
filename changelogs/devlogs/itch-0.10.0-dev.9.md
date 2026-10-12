<!-- Markdown copy of the itch.io devlog "0.10 dev builds: its own window, and powers that grow". The HTML original is posted at https://stelliro.itch.io/morkyn -->

# 0.10 Dev Builds, Part Two

Mørkyn gets its own window. Your powers grow by the rules.

## Since The Last Post

The last devlog ended at dev.6. Since then, two more dev builds went out (dev.7 and dev.8), and a larger batch is about to land. The hand-played games kept going and the issue log passed ninety entries. The 8B model also got a new job: making a few hundred abilities so their math could be checked by hand.

> Same rule, pushed into one more place: the model describes a power. The game does its math.

## Its Own Window

- **Morkyn.bat** opens the game in its own window, with no browser tab and no terminal left open. A boot page shows the startup log, then the menu loads. Closing the window stops the server and the model.

- The launcher's settings now live in the game: where it runs, the engine, the pipeline, ports, models, context size and GPU layers. You no longer need the terminal menu for any of them.

- Pop-outs (Player, Map and the rest) open as real windows that stay in sync with the game.

- On Windows 11 the title bars follow the theme, and the icon is the logo's Ø drawn as one thread of light.

- Terminal windows no longer flash open during play. A GPU check was opening several of them on every turn.

The browser still works the way it always did. The window is an option, not a requirement.

## Powers That Grow By The Rules

Abilities used to be written whole by the model: the name, the cost, and how they grow. We had the 8B make 79 of them and checked each one by hand. In 58, the growth math was copied from the example. Only 3 had no faults at all. In every game we played, no ability ever changed.

Now the work is split in two:

- **The model picks a kind of growth**: compounding, steady, soft cap, breakthrough, passive, tied to an item, or flat. It also picks a seed in plain words: slow, steady or fast; weak, ordinary or strong; and what grows.

- **The engine does every number**: the rank ladder, the XP for each use (more for risky uses), soft caps, walls, and what each rank does. The setup card shows the result, and you can change the seed and watch the ladder update.

- Using a power in play earns it XP, and the narrator is told where it stands. A turn cannot rewrite how a power grows.

After the change, all 36 growth lines in the same test came out clean.

## A Library That Learns

Next we rolled 125 abilities across four worlds to look for repeats. Inside a single batch there were none. Across separate rolls, the same handful kept coming back: "echo" was in 22 of the 125 names, and it showed up in every world.

- **204 hand-written templates**, twelve for each of seventeen themes: wuxia, cyberpunk, gothic, hearth, apocalypse, noir, frontier, court, academy, salvage and more. Each one passes the same quality check as a generated power.

- **Custom worlds mix themes.** "A neon megacity where corporate sects teach qi" draws from cyberpunk and wuxia. Each call gets eight fresh templates, the least used first, and none that are supernatural in a world without magic.

- **The model can still invent.** A new power that passes the check and is not a near-copy of one already stored is saved to your library and offered in later games. The more you play, the more the model has to work from.

First test on the 8B, with a custom "cyberpunk sects teaching qi" world (12 powers in 6 batches). The mix came out as cyberpunk 50%, wuxia 40%, academy 10%. Of the 12 powers, 6 were adapted from templates and 3 were new and stored. One stored power was picked again two batches later. The other 2 were fallback cards, drawn from the theme templates rather than the generic pool.

## From The Playtests

- **Death is real.** One test ran 44 turns after health hit 0. Now there is a "You died" screen, and an optional **Ironman** mode where death ends the story for good.

- **Asking a question no longer hurts you.** Talking is routine. Persuading, haggling and demanding still roll.

- **Work rolls dice** against your proficiencies, and a quest task you actually do in play finishes the quest and pays out.

- **The prose matches the save.** A price the story names is the gold that moves. A purchase you cannot afford is refused. A gain, a move or a sale the game refused is cut from the scene.

- **Buttons for what the story offers.** Accept or Decline a job. Go with someone who offers to lead you, or Stay. Travel to a place you were told about, or set it as your destination.

- **Towns hold together.** Roads meet across the edges of a town's cells. Walls appear only where a town really has them, with a Leave button to walk out. Shops gather toward the centre and farms sit on the edges.

- **Energy stops draining from talk.** Short walks cost what they really cost, and each power is charged everything its card lists.

- **Read aloud.** A Play bar can speak the story, paragraph by paragraph, with a local voice or a speech API. It is off by default.

- At phone width you see one panel at a time, and Map focus gives the map most of the screen.

## Built, Not Yet Wired

Thirteen systems are written and tested but not yet part of the game. Among them are markets and prices, trade agreements, currency by theme, hunger and thirst, wounds by body part, capture and restraint, a cast list for each scene, settlement visits, wild places, and a real-time clock. Each has a checklist for turning it on, and they will be added one at a time with a playtest after each.

## Still Rough

Some ability batches on the 8B still take a minute or more, because the quality check sends them back. Powers ranking up in play has so far been tested by the engine harness, not in a long hand-played game. That is next.

## Versions

**0.10.0-dev.7** and **0.10.0-dev.8** are tagged on GitHub. The window, the growth system and the library ship in the next dev build.

Next: wire in the parked systems one at a time, then a stable **0.10.0**, then **1.0** as a standalone download with a set of starter saves.

Changelog: [CHANGELOG.md](https://github.com/Stelliro/Morkyn/blob/main/CHANGELOG.md)  
Issue log: [docs/PLAYTEST_ISSUES.md](https://github.com/Stelliro/Morkyn/blob/main/docs/PLAYTEST_ISSUES.md)  
How the model and the game talk: [README, MLE](https://github.com/Stelliro/Morkyn#mle--the-m%C3%B8rkyn-large-language-model-engine)  
Source: [github.com/Stelliro/Morkyn](https://github.com/Stelliro/Morkyn)
