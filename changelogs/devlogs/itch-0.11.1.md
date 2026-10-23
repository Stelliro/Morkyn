<!-- Markdown copy of the itch.io devlog "0.11.1: a download, and everything the story makes is kept". The HTML original (Itch.io/Devlog-0.11.1.html, not in the repo) is posted at https://stelliro.itch.io/morkyn -->

# 0.11.1

A download for Windows, Linux and macOS. Everything the story makes is kept.

## Since The Last Post

The last devlog ended at 0.10.0-dev.13 and a launcher script that cloned the repo and built a Python environment. Since then: dev.14 and dev.15, then the 0.11 line, and 0.11.1 lands with this post.

The big change is how you get it. **Mørkyn is now a packaged game**: a Windows exe, a macOS app, and a .deb, an .rpm and an AppImage for Linux. No Git, no Python. The build is about 60 MB; the heavy parts come as packs you install from inside the game.

> Same question as ever, every turn: does the save still agree with the story?

## The Download

- **Runtime packs.** The model runtime is built per graphics card (CUDA, Metal, CPU) and downloaded once, from Settings → Updates → Local engine. The game never ships it. On Linux the CUDA pack carries the CUDA runtime itself, so a plain NVIDIA driver is enough.
- **A version picker, not an updater.** The game lists its releases and you choose one, newer or older. Saves and packs are shared by every version, so going back is one click.
- **One-click models.** LLM details → Local models downloads Hermes 3 (Llama 3.1 8B), Llama 3.1 8B Instruct or Qwen3 8B. Hermes 3 is the one we now test on: expecting less and getting more is the goal.
- **Linux.** A menu entry that opens the game in a terminal you can close to quit it, a Qt window as an optional pack (PySide6; nothing GPL goes in a pack), and a QR code for the phone address, because "http" read as "https" cost us an evening.
- **Settings stay put.** API keys and model and speech settings save per user (encrypted on Windows), not inside a save.

## What The Story Makes Is Kept

0.11 is about not losing things the story invents, and not fixing them in place too soon.

- **People are pencilled in.** Someone a turn makes is a sketch until a later turn brings them back. Twins made in one turn become one person; a sketch who is really someone known is merged into them; a sketch nobody returns to fades, and comes back as themselves if the story names them again.
- **Unnamed people and creatures are kept too.** A ghoul, a raider, a guard the scene shows acting gets a record, numbered by kind: Ghoul 1, Ghoul 2, Raider 1. "Ghouls lunge at you" is rolled once, and the story then says "Four ghouls lunge at you" and keeps to four.
- **The dead stay dead.** Death is a 0/1 state the narrator is told only when it is 1. The dead leave a body where they fell, in the place's records and the scene, and do not get up to talk. A death is recorded only when two differently worded checks agree, so one wrong "yes" from an 8B model cannot kill a character.
- **Places have insides.** A ship's hold is in the ship, a back room is in the tavern. A place you reach by leaving another ("I leave the clinic and creep into the subway tunnel") is filed where the scene ended, not inside the clinic. The narrator is told where you are as the first fact, every turn.
- **Jobs are filed as said.** In the words they were offered in, under the person who offered them, steps written as play happens, and what you are owed is a ledger the game keeps. Jobs are referenced by code (@Q1) like everything else, so a retelling under another name is the same job.
- **Acts come from grammar.** Your line is split into clauses and each is judged by its form, so only what you do now rolls a check, costs energy or passes the clock. Not speech, not plans, not what waits on a condition. Energy costs were rebalanced against past runs replayed through the engine.
- **One roll decides an attack.** The dice are rolled before the scene is written, the combat math follows the same roll, and a death the roll did not allow is refused. Gold leaves your purse only when the scene shows money change hands, checked twice.
- **Persuasion follows what you ask.** One small check judges how many people would refuse, so a plain question is trivial and a strongroom key stays hard.

## How We Work Now

The last post described runs that stop at the first fault. Two things changed in the method.

- **Every small question is measured before it is trusted.** The game asks the model short yes/no questions ("Is Beth alive at the end of this?"). Each wording is now run against dozens of real recorded turns on Hermes 3 first, and the ones that fail are reworded or dropped. We learned that an 8B is good at a positive yes/no about one name, and bad at lists, negations, rewrites and multiple choice. Several checks that looked fine with a mocked model were wrong a quarter of the time live; they are gone.
- **Every fix is reviewed by a sceptic before it lands.** One agent builds the fix in its own copy of the repo; another replays recorded turns against it and tries to break it. Three fixes this week were rejected and rebuilt because the reviewer found they took a move or a sentence away from the player. Nothing that cuts the player's own words or choices ships.
- **The turn checker asks the model nothing.** The broad "verify this turn" question invented rules the game does not have ("no killing", "no magic") and once patched a shot into a punch. The check is now the engine's own records against the draft.

The issue log stands at 164 entries, the suite at about 4,600 tests, and every turn of every test run leaves a trace: what the model wrote, every change to the save with the line of code that made it, every refusal, and how long each step took.

## From The Playtest

A friend played the Linux build for an evening, from a phone. Each of these came from that game and is fixed in 0.11.1:

- The map said "out of bounds" while the player stood well inside it: the world map is generated, not stored, and a move was being checked against the size of a stored one.
- The Settlement view could be opened in the wilderness. It is for the settlement you are in.
- History showed every turn but had no way back to one. "Back to this turn" now undoes every later turn in one press, and a rewind puts back the clock, the weather, the fight and the scene flags, not only the people and places.
- Closing the window left the server running, and the next open attached to the old build. Opening Mørkyn now replaces a server left behind.
- Hermes 3 writes its op lines in shapes Qwen never did ('NPC_NEW: "NAME" "Theo" "ROLE"...', 'MOVE: None'). They are read as the op form now, so no place called None gets made.

## Still Rough

- **Scenes still drift.** Sometimes the narrator tells the scene somewhere you did not go. A fix that re-drafts the turn is in the build but switched off: every way we tried to read "did the player ask to move" from a typed line missed some lines ("I shoot my way out", "I buy passage to Dunmere"), and a miss would take your move away. The next attempt asks you instead of guessing.
- **The attack's result line.** A rolled hit the prose forgot to write is being fixed by the game writing that one line itself, from the roll and the weapon. It is in review and did not make this build.
- **No speech pack yet.** The local voice engine we had is GPL and nothing GPL goes in a pack. Read-aloud works through a speech API for now.
- **No Hermes baseline yet.** The long runs were all on Qwen3 8B. The first 100-turn Hermes run is next.
- **Speed.** On a 12 GB card, 10 to 40 seconds a turn on an 8B model. The checks add time; we are fixing faults first and time after.

## Next

The fight's result line written by the game. Then money and items read by their own checker before and after each act, with real currencies: copper, silver and gold held as one number, or caps, or credits, whatever your world uses. Then the game asks before it moves you anywhere you did not say. Then a **Combat** tab in place of the map during a fight: who you are fighting, their health, and a target you pick. After that, theft and locked doors, and a stable **1.0**.

## Versions

**0.10.0-dev.14**, **0.10.0-dev.15** and **0.11.1** are tagged on GitHub with downloads. 0.11.0 was a local build and has notes only.

Downloads: https://github.com/Stelliro/Morkyn/releases · Changelog: [CHANGELOG.md](../../CHANGELOG.md) · Issue log: [docs/PLAYTEST_ISSUES.md](../../docs/PLAYTEST_ISSUES.md)
