# Player brief: stage-fantasy20 (Mørkyn, Hermes 3 8B as game master)

Purpose: a short live check that the fixes made after the fantasy100 run hold on the 8B:
money moves only by a stated sum (never by a die), stated payments and sales settle coin and item,
jobs are filed when offered and accepted (not from chatter) and pay on completion, a creature shown
only in the prose gets a row and your blow lands on it, and travel by `#L` code moves you.

You are the PLAYER of a text RPG. The game runs in another process. You play 20 turns (T001-T020),
in character. You never edit the game's code or its data. You never load or run the 8B model.

    RUN=/tmp/claude-1000/-home-stelliro-STELLIROS-WORKSHOP-Morkyn/c7ea9045-9604-4aaa-a408-d22fcb77143e/scratchpad/live/stage-fantasy20

The world: classic high fantasy. You are Wren Ashcombe, 22, apprentice of the late hedge-mage Hesper
in Thornhallow, a border town of the kingdom of Aldmere on the old King's Road, with ruins in the
Greywold hills. Hesper died owing the Chandlers' Guild three years of wax; you have until the harvest
fair to pay or lose the cottage. You carry Hesper's brass-bound grimoire. Your one spell is
Candlelight (1 energy). Skills: Spellcraft, Old Script. Money is copper / silver / gold
(1 silver = 100 copper, 1 gold = 100 silver); the purse is held as one number in copper.

## The loop

- `$RUN/status.txt` says what the game waits for: `player 007` means it wants your line for turn 7.
  The setup and opening take about 30 s; wait until status shows `player 001`.
- Give a turn by writing ONE file: `$RUN/inbox/007.txt` with your line (one line, first person,
  present tense: "I ask the guildmaster what Hesper owed."). Three digits. Never skip or reuse a
  number. Never write `STOP`.
- Waiting / sleeping: a line `!wait <minutes> <kind>`, kind `wait` or `sleep` (`!wait 360 sleep`).
- Codes: prose marks people `[[A]]`, places `[[L2]]`, items `[[I1]]`, quests `[[Q1]]`. In your line
  you may address a person (`@A`), go to a place (`#L2`), name an item (`!I1`) or job (`@Q1`).
- After writing, wait for `$RUN/turns/007.json`:
  `timeout 600 bash -c 'until test -f $RUN/turns/007.json; do sleep 2; done'`
  (or the Monitor tool if you have it). The 8B takes 10-40 s.
- Read the turn with `python3 -c` or `jq`: `narration`, `dice`, `before` / `after` (purse, health,
  energy, location, inventory), `engine.delta`, `engine.notes`, `used_fallback`, `seconds`.
  Deeper evidence: `$RUN/data/model_traces/<engine.trace>` (`model_trace`, `engine.ledger`). Read a
  trace only when the turn record is not enough.
- `$RUN/db/turn-010.md` (every 10 turns) is a readable export of the save.

## How to play

Play STRAIGHT, like a person who wants to get somewhere: never claim items, coin, powers or outcomes
you do not have; say what you try, not what happens. One intent per line, 1-2 sentences.

In 20 turns, aim the play at the fixed systems (in roughly this order, adapt to the story):
1. T1-4 talk and jobs: ask someone for work; when a job is offered accept it plainly and ask the
   pay. Check `engine.delta.new_rows` / the db export for a quest row. Address someone by `@code`.
2. T5-8 money: buy something stating a price in coins ("I offer three copper for the bread");
   sell something you hold; pay part of the guild debt. Compare the prose's coins with the purse
   in `after`. Also note any turn where the purse moves with no sum stated.
3. T9-12 travel: go somewhere by `#L` code, then out to the Greywold hills / ruins; watch
   `after.location`. Search a ruin; see whether finds reach `after.inventory`.
4. T13-17 fight: go looking for a creature; when the prose shows one, attack it by name ("I strike
   at the wolf"). Check a row was filed for it and the engine's result line names it, not a
   bystander; check its health.
5. T18-20: cast Candlelight once, one `!wait` rest, then report back on the job and ask to be paid
   if it is done (watch the payout reach the purse).

## What to record (create the files)

`$RUN/player-notes.md`: one line per turn right after reading it:
    T07 "<your line>" AT <location>. <2-4 facts: who is here with codes, purse/HP/energy if changed,
    jobs, anything odd>.

`$RUN/faults.md`: a markdown table:
    | Turn | Severity | Class | What happened (quote the prose / row) | Evidence (trace file) |
S1 = state wrong (save vs prose: coin, items, places, people rows, health, dice), S2 = player's
agency (narrator speaks/acts/decides for you), S3 = prose (reset, drift, echo of your line, codes or
engine text leaking, hour wrong). A repeat of an earlier class goes INSIDE that row as "(again T12)".
Quote the exact prose and save field. Clean turns get no row. NEVER stop the run for a fault.
Also mark the fixed systems that WORKED, in a short `## Worked` list at the end of faults.md, with
turn numbers.

## End

After T020 append `## Handover (end of T20)` to player-notes.md (where, who with codes, purse, HP,
jobs filed or unfiled). Then reply with: turns played, fault count by severity, the three worst
faults with turn numbers, and which of the five fixed systems held or failed (with turns).
