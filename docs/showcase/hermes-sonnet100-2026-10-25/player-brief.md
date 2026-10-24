# Player brief: sonnet100 run (Mørkyn, Hermes 3 8B as game master)

You are the PLAYER of a text RPG. The game runs in another process. You play 25 turns, in character,
then write a handover. You never edit the game's code or its live data. Everything you need is in
the run folder:

    RUN=/tmp/claude-1000/-home-stelliro-STELLIROS-WORKSHOP-Morkyn/f7b043fb-d5ad-42dd-93fa-2617f3608061/scratchpad/live/sonnet100

- `$RUN/status.txt` says what the game waits for: `player 017` means it wants your line for turn 17.
- You give a turn by writing ONE file: `$RUN/inbox/017.txt` containing your line (plain text, one
  line, first person: "I ask the tallyman what I owe."). Zero-padded three digits. Never skip or
  reuse a number. Never write `STOP`.
- Waiting / sleeping is a line of the form `!wait <minutes> <kind>` where kind is `wait` or `sleep`
  (for example `!wait 360 sleep` to sleep six hours, `!wait 60 wait`).
- Codes: the prose marks people as `[[A]]`, places as `[[L2]]`, items `[[I1]]`. In your line you
  may address a person by code (`I tell @A I never asked for rope`) or go to a place by code
  (`I head to #L2`). Use them in some lines, not all.
- After you write the line, wait for `$RUN/turns/017.json` to appear (the 8B takes 10-40 s, up to
  2 minutes). Wait with the Monitor tool if you have it (ToolSearch "select:Monitor"), otherwise
  run: `timeout 600 bash -c 'until test -f $RUN/turns/017.json; do sleep 2; done'`.
- Then read `$RUN/turns/017.json` (use `python3 -c` or `jq` to print the fields, it is small):
  `narration` (the scene), `dice`, `before` / `after` (gold, health, energy, location, inventory),
  `engine.delta` (what the save changed: player, clock, new_rows ...), `engine.notes` (what the
  engine refused or decided and why), `used_fallback` / `fallback_reason`, `seconds`.
  Deeper evidence for a turn is its trace: `$RUN/data/model_traces/<engine.trace>`
  (`model_trace` = what the model was asked and said; `engine.ledger` = delta, writes, swallowed).
  Read a trace only when the turn record is not enough to say what went wrong.
- Every 10 turns `$RUN/db/turn-0N0.md` is a readable export of the whole save (people with codes
  and places, places, quests, inventory). Read the newest one when you need to know who is on
  record where.

## How to play

Play like a person who wants to get somewhere, not like a tester ticking boxes. One clear intent
per line, 1-2 sentences, first person, present tense. Keep to what the character would do. Do not
narrate outcomes ("I kill the wolf"); say what you try ("I stab at the wolf's throat").

Across your 25 turns, exercise these systems (the baseline run found faults in each):
- Talk: greet, ask questions, refuse something, address someone by `@code`.
- Jobs: ask for work; when a job is offered, accept it in plain words and ask the pay; later report
  back and ask to be paid. Watch whether a quest row ever appears (db export, engine.delta.new_rows).
- Money: buy and sell, stating a price in coins ("I offer two copper for the herring"); pay a debt.
  Compare the prose's coins with `after.player.gold`.
- Travel: go to a place by `#L` code, to a named place, and out into open ground; watch
  `after.location`.
- Search: pick through salvage; see whether finds reach `after.inventory`.
- Fight: when a creature appears, name it in your attack ("I stab at the dire wolf"); if nothing
  attacks you in 25 turns, go looking for the beast in the marsh. Watch which row the engine's
  result line names and the creature's row/health.
- Rest: one `!wait` sleep or rest; watch the clock and energy.
- The ability Tidecount (1 energy): "I use Tidecount to feel when the flats will flood."
- A line that names two codes once.

## What to record (append to the two files; create them if missing)

`$RUN/player-notes.md`: one line per turn, right after you read the turn:
    T17 "<your line>" AT <location>. <2-4 facts: who is here with codes, gold/HP/energy if changed,
    jobs, anything odd>.

`$RUN/faults.md`: a markdown table (header once at the top of your section):
    | Turn | Severity | Class | What happened (quote the prose / row) | Evidence (trace file) |
Severities: S1 = state wrong (save vs prose: gold, items, places, people rows, health, dice),
S2 = player's agency (the narrator speaks or acts or decides for the player), S3 = prose
(continuity reset, drift to another place, echo of your line, codes or engine text leaking, stock
phrases, hour wrong). One row per fault; when it is the same class as an earlier row of yours,
write "(again T17, class ...)" INSIDE that earlier row rather than a new row. Quote the exact
prose and the exact save field. A clean turn gets no row. NEVER stop or restart the run because of
a fault: log it and keep playing.

Also note timing: `seconds` of any turn over 60 s, and whether `used_fallback` was ever true.

## Start and end

Start by reading `$RUN/turns/000.json` (the opening), the newest `$RUN/db/*.md`, and the end of
`$RUN/player-notes.md` (the previous player's handover, if any) so you continue the same story.

After your last turn, append to `$RUN/player-notes.md` a `## Handover (end of Tnn)` section:
the state of the story (where, who with codes, gold, HP, debts, open jobs filed or unfiled),
the systems you exercised, what the next player should do, and what to watch. Then reply to the
coordinator with a short summary: turns played, the fault count by severity, the three worst
faults with turn numbers, and anything that worked well.
