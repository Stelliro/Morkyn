# Saltmarrow on Qwen2.5 7B: runs 30-32, findings (2026-10-14)

Same setup as the other 7B runs (docs/showcase/saltmarrow-setup.json), Qwen2.5 7B Instruct
Q4_K_M as the GM through MLE, Claude as the player, `tools/api_bridge_playtest.py --local-model
... --viewer-port 8790`. All data isolated in the session scratchpad. No run is clean yet, so
there is still no baseline. The loop was stopped at Stell's ask after run 32 T4.

Every fix below has a test, was replayed over all saved runs (5-32) with each change read, and
passed the full suite with only the 15 known failures. Nothing is pushed.

## Run 30 (stopped at T15; fixes merged at 013e074, docs 46425c2)

- T0/T15 (MAJOR): "Help with moles" had the one step "Go to the tannery"; a quote naming the
  trouble finished and paid it while Isk said the traps were empty. Fixed 85904f5 (fork R22): a
  walk-only work job gets its work step, the last step needs an outcome or the player's own act,
  the player's "not yet" stands.
- T3-T10: "Set the first one where the earth is freshest" rolled mining on the word "tunnel",
  failed and cost a hurt leg the prose never showed; the narrator was told only "mining,
  failure". Fixed 8f8aefd (fork R21): each check ships `for` and `means`; trap setting is
  survival; a check's self-injury the prose does not show is not applied (ledger note).
- T7, T14, T15: degenerate "mole" draft (claws on a human, paraphrased echo of Isk's line, her
  act given to Dunstan, a word cut off in a quote, "It's time to make a move"); orphaned replies
  after "then make your way"; first-person narration. Fixed 31ed3ce, aabc5d8 (fork R20).
- T8-T12: Dunstan's job overwritten to "runner" then "local"; "the hilt of your knife" with no
  knife. Fixed 44df55d.

## Run 31 (code ae10210; stopped after T7, five fixes behind main)

- T1: the refused wood find dropped, but "It's a small piece, but it might be useful." stayed.
  Fixed 42f4740.
- T2: 'Morning. You stop ... "Morning. Whose grave ..."' (one-word echo). Fixed 1227584.
- T4: "Travel action with no MOVE op ... stayed put" Note in the history on a kneel-and-help
  line. Fixed 1227584 (Note only when going was the line's point; ledger keeps it).
- T5 (MAJOR): ", then you turn and walk back towards the town" ran on into a new encounter (Kit
  Everly) and an invented 'You nod, "...Thanks for the offer, Kit."'. Fixed aeeaffb.
- T7 (MAJOR): "I read the salvage notices ..., looking for the pay" never "found", so no cut;
  the prose walked Isk into the reeve's office and got her a job there. Fixed b4d88ca.
- Not fixed, minor: T2 "You examine the grave" (small invented act); T3 Ermengarde repeats
  "the mud's soft" a third time (short line, under the repeat bar); T6 persuasion roll on a
  plain question (#88, Stell's call); T6 stale re-introduction of Ermengarde at the end.

## Run 32 (code b4d88ca; stopped after T4 at Stell's ask)

- T0: a two-way menu split across two sentences ("You could ... Or you might ..."); script
  label 'Maud Venn [[A]], tallyman: "..."'; a drawn NPC "Tamsin" for the figure the next
  sentence names as Maud; "Coldwell and Sons, a woman" nearly read as a person "Sons". Fixed
  48fc1a1.
- T1-T2: the 7B glued "theflats"; the engine stored a place "Theflats" and a fact about it.
  Fixed cdea3b0 (split before the draft is read).
- T2: "what does the run pay?" was answered with two tally runs and "a few coppers", but the
  quest parser was never asked, so no job exists. Fixed 6d1d5d5 (a pay question opens the gate).
- T4: walking to "the northernmost storehouse" put Isk in a new venue "Saltmarrow Supplies"
  (named from "goods and supplies" inside it). Fixed b70aaf5 (the player's own words name it).
- Open: T3 Maud "hands you the sticks" but the tally sticks never reach the inventory (no GRANT
  op; the take reconcile only reads player take verbs, and "I hold out my hand for" is not one).
- Open: T1 a place "Northernmost Flats" was made, apparently from the cut tail; not checked.

## Process notes

- C: filled (0 bytes) mid-suite: test modules never remove their `mkdtemp` dirs, 14,274
  `morkyn-*` folders in %TEMP%, about 20 GB. Old ones deleted (15 GB freed).
  `tools/run_suite.py` (ae10210, 1227584) now runs the suite with its temp in a per-run folder
  on the repo's drive and deletes it after; CLAUDE.md points to it.
- My slip, 13:29: a sanity check called `app.db.init_db()` without the isolated data env, so the
  startup migrations ran on the live `data/world.db`. As far as known only schema migrations
  ran, the same the game runs at startup; there is no backup to compare.
- Run notes per turn: session scratchpad `findings-saltmarrow-7b-r31.txt` / `-r32.txt`; the
  saves and traces are there too (`saltmarrow-7b-r30` .. `r32`).

## Run 32 open items, fixed (2026-10-14)

- T3 tally sticks handed over: fixed f4f3f01 (holding out a hand for something reads "hands you" as the answer).
- T1 "Northernmost Flats" from the cut tail: fixed f35b455 (a LOC_NEW named only in the cut part is not stored).

## Runs 33-37 (each stopped once its save was wrong; fixes committed before the next run)

- Run 33 (f35b455), stopped T2: a trip with work at its end ran on back to the trading post and the
  MOVE stood. Fixed 4f050bc.
- Run 34 (4f050bc), stopped T2:
  - T1: "I walk over to Kit at the edge of the flats" minted "The Flats" and moved Isk; "You thank
    Kit and make your way towards the flats" ran on. Fixed 2a93f18.
  - T2: a coin pulled "from the debris" not granted; a drawn "Bryony" for the voice the cut part
    named Ivo Garner; "The Flats [[L2]]' surface". Fixed 92f8254.
- Run 35 (92f8254), stopped T1 (MAJOR): the verifier's JSON put the dialogue in single quotes, so
  invented player lines passed every speech pass; a question ran on into a trip, a repair and a
  move into the cookshop. Fixed 2ea3c4a.
- Run 36 (2ea3c4a), stopped T7:
  - T2: Isk's untagged question read as Emrys's (035daeb); "You thank Emrys" never said (8def2cf).
  - T3: a lead-in left without its repeated line (8f1301a).
  - T6: persuasion vs Emrys for a question put to Tobin, "not Emrys" (771216b).
  - T7 (MAJOR): purse 12 -> 16 from a coin handed over only in the cut part (812e867).
  - Not fixed (model, noted): the harbour "bustling with ships" in a town the sea left; Tobin's
    boat became "a fisherman"; Emrys answering for Tobin; an invented thought quoting a line never
    said; the Copper Plough described open while the engine has it closed.
- Run 37 (812e867), stopped T3:
  - T1: a one-word echo after the line's tag (d9093b6).
  - T2: a pay question created the job "Move old planks to the shed" (the run 32 fix working).
  - T3: the job taken and done in one line, then paid, was left open as "paid ahead"; a new
    "Saltmarrow Shop" beside the named carpenter's shop. Fixed fc19b26.

Every fix has a test, a replay over all saved runs and a full-suite pass with only the 15 known
failures (the dice-audit flake tripped once and passed alone).

- Process: a probe cleanup was refused by the safety check; `D:\morkyn-probe` (a few MB of my
  probe data dirs) is left for Stell to delete. Probes now use a scratchpad folder.

## Next

Run 38 on fc19b26 or later.
