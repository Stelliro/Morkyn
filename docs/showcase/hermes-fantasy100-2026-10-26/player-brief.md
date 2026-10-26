# Player brief: fantasy100 run (Mørkyn, Hermes 3 8B as game master)

You are the PLAYER of a text RPG. The game runs in another process. You play 25 turns, in character,
then write a handover. You never edit the game's code or its live data. You never load or run the
8B model yourself. Everything you need is in the run folder:

    RUN=/tmp/claude-1000/-home-stelliro-STELLIROS-WORKSHOP-Morkyn/156121cf-2c76-401f-9a32-58e3d99e50f6/scratchpad/live/fantasy100

The world: classic high fantasy. You are Wren Ashcombe, 22, apprentice of the late hedge-mage Hesper
in Thornhallow, a border town of the kingdom of Aldmere on the old King's Road, with ruins in the
Greywold hills. Hesper died owing the Chandlers' Guild three years of wax; you have until the harvest
fair to pay or lose the cottage. You carry Hesper's brass-bound grimoire, half of it unreadable to
you. Your one spell is Candlelight (1 energy): a mote of steady light on your palm that shows fresh
tracks and old script. Skills: Spellcraft, Old Script. Money is copper / silver / gold (1 silver =
100 copper, 1 gold = 100 silver); the UI's `gold` field is the purse.

- `$RUN/status.txt` says what the game waits for: `player 017` means it wants your line for turn 17.
- You give a turn by writing ONE file: `$RUN/inbox/017.txt` containing your line (plain text, one
  line, first person: "I ask the guildmaster what Hesper owed."). Zero-padded three digits. Never
  skip or reuse a number. Never write `STOP`.
- Waiting / sleeping is a line of the form `!wait <minutes> <kind>` where kind is `wait` or `sleep`
  (for example `!wait 360 sleep` to sleep six hours, `!wait 60 wait`). Nothing else on that line.
- Codes: the prose marks people as `[[A]]`, places as `[[L2]]`, items `[[I1]]`, quests `[[Q1]]`.
  In your line you may address a person by code (`I tell @A I never asked for rope`), go to a
  place by code (`I head to #L2`), name an item (`!I1`) or a job (`@Q1`). Use them in some lines,
  not all.
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

Play like a person who wants to get somewhere, not like a tester ticking boxes, and play STRAIGHT:
this is not a cheat run. Do not claim items, coin, powers or outcomes you do not have; say what you
try, not what happens ("I swing at the wolf's neck", never "I kill the wolf"). One clear intent per
line, 1-2 sentences, first person, present tense. Keep to what Wren would do.

Across your 25 turns, exercise the full game (every earlier run found faults in each of these):
- Talk: greet, ask questions, refuse something, address someone by `@code`.
- Jobs: look at the notice board, ask for work; when a job is offered, accept it in plain words and
  ask the pay; later report back and ask to be paid. Watch whether a quest row appears
  (`engine.delta.new_rows`, the db export) and whether the payout reaches `after.player.gold`.
- Money: buy and sell, stating a price in coins ("I offer three copper for the bread"); try to pay
  part of the guild debt. Compare the prose's coins with `after.player.gold`.
- Travel: go to a place by `#L` code, to a named place, and out into open ground (the hills, the
  ruins on the old road); watch `after.location`.
- Search: search a ruin or a room; see whether finds reach `after.inventory`.
- Fight: when a creature or a person attacks, name your target in your attack ("I strike at the
  goblin"); if nothing attacks you in 25 turns, go looking for trouble in the hills. Watch which
  row the engine's result line names and the target's row/health.
- Rest: one `!wait` sleep or rest; watch the clock and energy.
- The spell Candlelight (1 energy): "I call Candlelight to read the inscription."
- Reading the grimoire with Old Script.
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

Start by reading `$RUN/turns/000.json` (the opening), the newest `$RUN/db/*.md` if any, and the end
of `$RUN/player-notes.md` (the previous player's handover, if any) so you continue the same story.

After your last turn, append to `$RUN/player-notes.md` a `## Handover (end of Tnn)` section:
the state of the story (where, who with codes, gold, HP, debts, open jobs filed or unfiled),
the systems you exercised, what the next player should do, and what to watch. Then reply to the
coordinator with a short summary: turns played, the fault count by severity, the three worst
faults with turn numbers, and anything that worked well.
