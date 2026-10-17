# Saltmarrow on Qwen3 8B: findings (2026-10-15)

Same setup as the 7B runs (docs/showcase/saltmarrow-setup.json), Qwen3 8B Q4_K_M
(`D:\morkyn-stage-models\Qwen3-8B-Q4_K_M.gguf`) as the GM through MLE, Claude as the player.
Testing order (Stell): 8B until no issues, then the 7B. Mode: play long, log faults by class
(`D:\STELLIROS_WORKSHOP\Morkyn-playtest-archive\2026-10-14-8b-runs\classes.md`), fix each class at
the one place it is decided, replay every saved 7B and 8B turn before committing.

Every fix below has a test and passed the full suite with only the 15 known failures (the
dice-audit flake tripped twice and passed alone). Runs 1-141 shipped in `0.10.0-dev.13`.

## Infrastructure

- Run 1: the opening took 891 s. The auto context window fit the free GPU memory at load with
  ~0.6 GB to spare (22,528 tokens; the 8B's cache is 147 KB a token, 2.6x the 7B's); desktop apps
  took the rest and the cache spilled into shared memory. The budget now keeps 1.5 GB free
  (1b7a62a): the 8B opens at 16-18k and turns take 10-60 s.

## Class fixes

- **The player's inner life and words** (C3, the 8B's commonest fault):
  - invented resolve, feelings and inner voice read by the thought check: contractions, lead-ins,
    feelings as a weight or a pull, states of mind, "A part of you knows", a thought as the subject
    (6eb0995, 3a5bb5d, 2210435); touch, the body, being watched and world news stay;
  - curly apostrophes read as straight ones (26e1eb8);
  - a restored line takes "ask" only when it asks (6eb0995); a piece of the line said twice goes (66639a0);
  - a retold typed line is an echo; the narrator planning the next steps is a decision (c4ea0ec);
  - a reported question must share words with the player's line (c9d8ab4).
- **State needs evidence in the prose** (C1):
  - a gain the prose says nothing of needs the line to ask for that item (3a5bb5d);
  - TAKE says it is a loss; a TAKE of an unowned item is a gain claim the grant checks judge (8c4be70);
  - unowned carried tools ("your lantern") go like unowned weapons (3a5bb5d);
  - a new person must be named by the narration or spoken to, not only mentioned in a line (175a3c4);
  - a misspelled known name is that person ("Harbour Reevec") (6eb0995);
  - the player's own debt is not work offered (de53653); jobs are judged against the shipped text (ae124a3);
  - a routine social roll earns no XP (e9d092b).
- **Scenes and movement** (C2, C6): any motion verb counts as the going for the trip guard; the
  travel Note needs a named place (09063e5); a venue the setup names is plausible whatever the
  settlement's size ("a village has no guild hall" in a guild town) (722430a).
- **Checks** (C4): not against someone the line leaves behind or asks past (0099f7a).
- **Text** (C5): item codes only on the player's things (2210435); a scene that stops mid-sentence
  is cut back (9abda50).

### Runs 6-13 (2026-10-15)

No run has gone past T5 clean yet; each restart came when the save went wrong. All fixes have a
test in tests/test_8b_run_classes.py or tests/test_7b_run6_places.py and a replay over the saved
turns, comparing against the committed code.

- **Words and acts the player did not write**: a reason clause ("that might fetch a price") is not
  the act (f9f8ebe); the player's line said once is said, a reworded copy goes (b82b39f); the half
  kept after a cut must be a clause, not "The knowledge that ..." (1bb06e1, a710633); a weighing
  with no one else's mind in it ("the idea of dealing with them is tempting") is the player's
  (ab3821a); an invented "As you turn to leave," lead goes and the world's half stays (f9af7d5).
- **Items and gold**: a partial verifier patch keeps the draft entries the prose shows (9820835);
  "a strange collection of items" is no collecting (a9359c7); money promised or wanted ("will pay
  handsomely", "itch for a coin") backs no gain (b82b39f); "do you ever buy ...?" is the other side
  buying (477d5e2).
- **People**: no blunder line with no one to offend (f9f8ebe); someone met at the end of a walk
  stands there (67b1594); a name bound to "a woman" pins she, and "the woman" resolves to her
  (67b1594); someone talked to whose LOC is no known place is in the scene (477d5e2).
- **Places**: no pursuit of a path or road (88cb9ff, ad2f2c8); "The Boar at Saltmarrow" is the
  Boar, not the town (d3ac66c); a MOVE to where the player stands is no refused trip (1bc0cca); a
  walk a few words before "toward the old docks" reaches them (d661a9b).
- **Verifier**: the naming rule is for other people; the player needs no name (d3ac66c, 47 s lost
  once in 450 replies).

### Runs 14-24 (2026-10-15)

Same picture: each run finds a new shape by T0-T3, the save goes wrong, and the run restarts.
Turns stay fast (10-40 s).

- **My own slip, found in run 15**: the left-behind and stranger-call rules from runs 5 and 7B 36
  never worked in play. They read names by their capital, the real caller lowercases the line,
  and the tests called the inner function with the cased line. Fixed (5ab1109); the replay shows
  exactly those three cases changing.
- **People**: a figure asked about ("Is it a person?") seeds no one (7f5cb1c); "the kind of person"
  is no one new (d0bc4b0); "They are a lean man" is the figure just seen (f92d658); someone shown
  in the scene stands in it (e092a35); a figure bound to a name this turn can give the job it
  offers (f941391).
- **Player's words and acts**: the player's own question is not narrated (7f5cb1c); a restored
  split line is said once (e06b3be); a cut leaves no pronoun stranded (2b6f036); a look at oneself
  is a gesture (b31657a).
- **Items**: stowing is taking, and a second verb on the same "you" is read (a7298db); "handed it
  to you" and "bit into it" (e092a35); a take that slips from your grip is no gain (c8d0ca9);
  "worth the haul" asks for it (a506a17); a tool from nowhere in the player's sentence goes
  (1f95eef); "the mother's reckoner" is your mother's (e5b96cd).
- **Places and moves**: what the line leaves is no destination (5ab1109); speech never asks to go
  (1fdf0e2); a MOVE to here is no refused trip on the town path, or beside a WALK (8a8f7ab,
  e97a4e5); filler words between a place's words (e2a69fb); picking your way down is a walk
  (727ba2d); the place crossed and the steps outside are no destination for the stayed-put Note
  (7a7c428, 4941bf6); a dropped WALK reads as a map walk (8f76a4c).
- **Checks**: water is no animal (1118358).
- **Records**: a fact the scene never shows is no record (e97a4e5); the debt runs the way the
  backstory says (f69e9ed, a narrow repair: the 8B inverted it in three openings).

### Runs 25-37 (2026-10-15)

Runs now go further (run 36 to T5, run 37 to T6) with a job taken and worked: tally house, offer,
acceptance, a walk to the flats, digging, the shells carried back.

- **Jobs**: "what work" asks for work, so the parser reads the answer (0b6b97d); the job taken by
  its subject ("I'll take the Stormborn") is taken (06c7dff); a mark on a question, a remembered
  promise or a figure nobody named are no offers (4920f08, ddfe9b0); the tally house is entered,
  not a salvage yard minted from the owner's trade (65fc760, 11a6f17, 749a89b, 77bf6f3).
- **Rewards**: talk earns no XP; "not_combat" had counted as a fight on every peaceful turn, and
  a proposed new job as a quest step (08ba801); a sum said in speech is no pay (5abd4a2).
- **Checks**: water is no animal, where a ship lies is no lie, the water creeping is no stealth,
  stairs are walked (1118358, 02b766d, dc25fd5); leaving the place leaves the talk partner
  (2fe71df).
- **Words and names**: "Inside" is no name and no speaker (ddfe9b0, c20b7f7); a name that is a
  word of the person's own job is the job (c20b7f7); the verifier may let others name the player
  (d98a7c5, my own run 9 clause had been read the other way); a short NPC line is not the
  player's, and the other half of a split line keeps its capital (06c7dff, 5240cdb).
- **Items and places**: stowing is taking (a7298db); the plural handed over is the whole stack
  (1ba5b53); someone else's tunic gets no item code (c45a92d); the player's stated restraint
  stands (ab64cc8); the walk ends at the last place named (dc25fd5); other spellings of here are
  here (88693cd, 300bdf3).

### Runs 38-52 (2026-10-15)

All fifteen were stopped at T1-T4 on a state fault and restarted on the fix. Runs 47 and 51 got
furthest (job offered, taken, walked toward). Each fix was replayed over the saved drafts first.

- **People**: the name the prose tells wins over the op's (9c5dae1), and a name told as "his name
  is ..." is stored at all (3dcebcc); a figure named by the op's role ("the tallyman") is that
  person (4bcca47), but a figure in apposition to the job of someone already here is them, not a
  new face (d6e8b17); someone met where the walk ends is there even if met before (f103cb0); a
  named person keeps their own pronoun after a cut (f5078ab); "Tallyman" is a job with any role
  (de33522).
- **Talk**: a TALK line the prose never shows is not logged; the openings' unsaid "You're late,
  Flat-runner" was being echoed word for word in later scenes (05653b4, 38 of 356 saved lines);
  one line voices an indirect request, even after a narrator beat (3dcebcc, 0745269); the beat
  that only led into a cut line goes with it (9c5dae1); a repeat is the other person's (da707f3).
- **Places**: only the player's going makes a place ("the sound ... echoes through the hollow
  alleys" made "Hollow", de33522); the way is not the end ("along the shore path toward the Hollow
  Reach", 359a78c); another spelling of a known place is that place (514fb1b); the player's own
  three-word name for a building holds (4bcca47); leaving where the walk went is a new move
  (0745269).
- **Money, items, rewards**: a question asked pays nothing (d6e8b17); asking where a thing is does
  not take it, and a spoken "I'll take it" agrees (c6fd3b1); an errand in town is no discovery,
  and a revisit reads the real visit count (e0e0cd0); a spoken line, tagged or not, shows nothing
  arriving (f5078ab, 359a78c); a mark whose giver is elsewhere needs an offer (05653b4), and a
  giver shown by their job is in the scene (da707f3).
- **Prose**: a relative clause gives a kept tail no verb ("The promise you made to the tides",
  aff3328).

### Runs 53-72 (2026-10-15)

Runs now reach T7-T11 with state intact: run 54 took a dock job, worked it, finished it and was
paid (T7); run 72 went to T11 at the shoals with nothing wrong in the save after T9.

- **People**: someone reached by code alone, or shown after the arrival with no op at all, goes
  where the walk ends (f96eda3, 068f7ad), which is likely behind the "new face at the desk" drift
  of runs 40-51; a drawn name fits the sex the figure was shown with (98b7087); a merchant ship
  is no merchant (3dd75fe); someone talked about is not shown (1f4730c); a vague figure is the
  one the scene names later (79ab772).
- **Jobs**: the job's own verb takes it ("I'll clear the Stormbreaker", e56e7c2); a quote
  written inside the reward is the job's (19434d1); a refusal is no offer ("I don't deal in
  charity" had read as "Deal.", 7d40e79); an offer is spoken whichever way its apostrophes lean
  (44a8485); the same named job is the job taken (5a71d7c); no markdown in a job's name
  (68e3a79); the last of the hold is done (c0307a1).
- **Rewards and money**: the face met on an errand is no find, and taking a job or a step with no
  result earns no XP (3dd75fe, 9f6339d, 748ccd3); a job that pays, or a promise ("you'll be
  paid"), is no coin (748ccd3, 749e760).
- **Items**: a part held ("the end of the crate") is no thing (c0307a1); lifting it out takes it
  (68e3a79); a spoken "I'll haul the beams" takes nothing the prose does not show (749e760).
- **Places**: a new place walked to is in town (c0307a1); a room of the building one stands in
  is a place to go (4c3cd73); a clause with its own subject is not the player going (f6f0d08); a
  place passed is not the one entered (755df01); the walk's end is a place, not a thing looked
  for (3740e0a).
- **Words**: "and you do", "you choose the first", "you agree to", "you accept the offer" are the
  player's to say (5a71d7c, 068f7ad, 44a8485, b6d610a); a shorter saying of a typed line is that
  line, in its place (3ff0604); "the player" is "you" (98b7087); a code that names nothing goes
  (f6f0d08).

### Runs 73-80 (2026-10-15)

Run 79 took a hauling job, did it and was paid at T5; runs 73 and 80 reached T6-T7. Each run
still turned up one state fault, now mostly in movement and job offers:

- **Movement**: the place asked for comes before a lane on the way (30183a3); a thing lifted out
  is no exit (6638623); the place stood in is no destination asked for (8f8064e); a place said,
  or a job named, in speech is no walk to it (72b3afe, 8df1ad5); a room of the building one stands
  in can be gone to (4c3cd73).
- **Offers**: a debt is no job, a task set is one (94aaf08); the player's own question, and the
  giver telling it back, offer nothing (184dd08). Both were judged against each run's stored
  people; one real notice-board job in 7B run 29 is lost, as it had stood only on a wrong quote.
- **Money and items**: paying mind is no pay, and one word off a known place is that place
  (6638623); a promise is no pay and a spoken "I'll haul" takes nothing (749e760); a job at the
  yard is a job, not a yard (8498223).
- **People**: a figure in another trade is not the one sought, and a job-named person takes the
  sex shown (30183a3, 8498223); a name after "the <job>," names, it does not call (038b0a6).
- **Prose**: "the player" is "you", the 8B's glued bracket ("the(guild's") is mended (98b7087,
  8f8064e).

### Runs 81-112 (2026-10-15 to 2026-10-17)

Goal set by Stell on 2026-10-17: 100 turns on the 8B with no issues. Runs still end in T2-T7 on
one state fault each; run 106 reached T7. From run 97 a run is stopped only for a state fault or
a new class, not for the logged prose classes below, which appear in every run.

- **Movement**: an "out" of another verb ("call out") is no exit (6abb010); a walk toward a place
  is no arrival, "Inside," is (7240412); a scene cut where it stops keeps the player there, and a
  place only said in speech is not reached (f72b3f8).
- **People**: a known person elsewhere whom the prose never names keeps their place and job, but
  one shown by their job is shown (5056d74, addeea2); a common-noun name ("Tallyman") is a job
  (173c2f0); a figure inside a description ("the kind of scent that clings to a man") is no one
  (e9d758f); an employer word in a role ("guild") is no figure (cd5681e); a figure named after a
  dash ("a figure at the bow, Captain Miren") is that person, and other figures beside named ones
  are more people (70c84ab); a job word is no part of a name ("Tallyman Darrick", 82762f7); a
  name only spoken of is not the hooded figure (8990e01); of several figures the one inside is
  the ops' person (75cdb85); people the walk meets at a place made this turn, new or known, stand
  there (addeea2, b1e5c2f); someone the turn talks with and shows by code is here (6329e81); a
  name in the player's line for someone elsewhere is marked "not here" in the note (45cfbc1).
- **Places**: a short name, or one word left out, of a known place is that place (04397c6,
  8990e01).
- **Jobs**: a "You ..." line spoken to the player is an offer (d726d8c); a giver named by job
  resolves to its one holder (28aa8f8); the parser shape's own wording is no value (d56f3cc); an
  open offer told again is that offer, and its card takes the telling (ef031c9, 704edda); "I'll
  take that one" takes it, a hedge does not (e6ad5ae); a look at the job finishes nothing
  (1635ab3); the giver's own offer sentence grounds a job (82762f7); a service the player buys is
  no job (1d56760); the parser gets only the player's line (704edda).
- **Money and items**: readiness to pay moves no coin (cd5681e); someone else counting out coin is
  no payment (f72b3f8); a thing handed over under another noun ("the slip") is the item
  (28aa8f8); accepting a job is no ask to take things (f72b3f8); a contract picked up is a thing,
  a place is not (0b0a4fd, 40a5c02).
- **Checks**: someone left behind or walked away from is no opponent (fe77a4f, 1635ab3).
- **Verifier and prose**: a verifier patch cut by its token cap keeps the draft's prose
  (515ff81); a speech lead with no line after it goes (73ff3cf); both halves of a line taken back
  from another speaker go (24d33e5); a refused gain never cuts the player's own words (0b0a4fd).

### Runs 113-141 (2026-10-17)

Still one state fault per run, found in T1-T7. 12 of the 29 fixes are in the quest parser.

- **Jobs**: a job just taken is not two (ecbbb22); taking by a word of the title goes by stem
  (64bc0fa); a giver asking what work is wanted, or demanding proof, has set none (3a8b1d6,
  61767ce); the giver naming the work is the offer (1a1f795); one apostrophe for a job told to you
  (e406f59); a start wished for is no start (2171b56); a job with no task, or only work in
  general, is no job yet (3fd98c2, 2b36e60); a plain title from another giver is no duplicate
  unless the steps agree (2d14984); a line the prose gives the player is no offer (5bdf0c9).
- **Movement and places**: a size band is an amount, a place passed is no move (7b3a862); a sign
  passed is not the door gone in (76693ed); a placeholder is no place (cda643f); a replaced move
  leaves no place behind (61767ce); a place named in passing joins the town (d595ee0); a place
  passed on the way in is not the venue entered (f70e230).
- **People**: the player's name is no one else's (334b641); a sign's possessive is no use of a name
  (b71ae56); the ops' name fits the sex the prose shows (af58b2c); someone said not to be there is
  not there (bdd4846); the one talked to comes along to an unnamed speaker (fc0e5d4).
- **Money**: a chance to pay moves no coin (9fe15f9); coins lying in the scene move nothing
  (8ef2e8c).
- **Player's words**: a line said is not also retold (3e33570); a sentence inside someone's quote is
  theirs (cf8b9c1); an echo of the player's line goes (770f673); speech and acceptances given to the
  player go (1604fb7, 83a28a6); the engine's clock after a dash goes (40beefa).

### Run 142 (2026-10-18): the engine-first offer pass, live

Six turns on 8ddb63d plus the fixes below, watching `quest_fill` / `quest_check` in the traces.

- T2: the tallywoman's "there's always the dredging ... If you find something worth salvaging, you
  get a third of the value ... Just bring it back" was the one candidate (speaker unknown: she was
  minted this turn). Fill 7.2 s, check 2.9 s, both yes; "Dredging the Drowned Town" offered. The
  keyword judge alone would have refused it (`no_offer_in_exchange`). The narrator's bare
  "Salvage Contract" mark still reached the apply step through world.py's own mark merge and was
  refused only for want of a quote: closed, both merge points now use `quest_offers.marks_to_merge`.
- T3: typed acceptance taken by the engine; no candidate in Veyra's answer; 0 asks.
- T4: the player worked the step and the gate stayed shut: it read the title ("Dredging the
  Drowned Town"), not the step ("Locate the drowned town's wreckage along the coast"). Fixed:
  `open_quest_step_named`.
- T5: the fill said yes to "You bring it to me, and I will decide its worth" and the check said
  `specific: no`; nothing filed. That is the two-stage behaviour the split was for. The progress
  check rightly said the step was not shown finished. 3 asks, 9.3 s.
- T6: a question about the player's mother; no job words, 0 asks.
- Other faults, by class: a forklift in the opening (anachronism, prose); the coast is no place,
  so working the wreckage moved the player back to town (movement); "I carry the rusted compass"
  rolled navigation and hurt the player (#102, fixed: the noun-only craft triggers want the
  thing used); Veyra became "the
  barkeep, Emery Kemp" at the tally house (C10 person swap, open); a FACT op wrote "The player
  has accepted a salvage contract" while the job was only offered (state claim without evidence;
  the engine ignored it, the fact row stands).

## Logged, not fixed

- Now the largest class by far: the player's inner life and past invented by the prose ("your
  heart pounding", "You had been here before", "The realization hits you", "a reminder of the
  choices you've made"). Several per run. Waiting on the outcome-reader decision in
  docs/showcase/prompt-review-2026-10-14.md; a pattern cannot tell these from true backstory.
- Rolls narrated against: r126 T5 was told `athletics failure, the work is not done` and wrote
  "you pull free a bundle of rope ... it's worth hauling back". The state stayed right (no rope),
  the prose did not. Same outcome-reader decision as the class above.
- C9 past tense on whole turns, most runs at least once.
- C10 scene drift: r72 T10 put the channel-side talk inside Edith's "cramped shop".
- r55 T5: "He gestures for you to follow him, and you do" stays when the player's own line had a
  walk in it (the walk rule lets the follow ride on it).
- r63 T5: "the flats runner" became "The Flats [[L3]] runner" (a place name used as a modifier
  got its code).
- C10, repeated in runs 40-51: at T2 the tallyman met at T1 is replaced at his desk by a new face
  (a woodseller, a "Captain Veyra"). The state stays right; the prose drifts.
- A job picked from a list offered the turn before ("The rusted tools, then") reads as no offer
  in its own turn (r52 T3).
- C9 voice: a turn in past tense (r2 T3); NPC lines without quote marks (r4 T4).
- C10 model continuity: people renamed or swapped mid-scene (the shadow man Gregory -> Osric),
  stock dodges ("You're not here for the tide, are you?") instead of answers, scene drift.
- Invented memories of the player's past: a pattern cannot tell them from true backstory; candidate
  for the outcome reader in docs/showcase/prompt-review-2026-10-14.md.
- #88: persuasion still rolls on plain questions (Stell's call).
- Judgements and feelings for the player with no clause shape to read: "The coin's real, and the
  risk is worth it", "you've made your name there", "the weight of the offer settling in your
  chest" (r10 T3, r13 T2-T3). Outcome-reader candidates, like invented memories.
- XP from the model's own op on plain talk (r12 T1: 14 XP for a question).
- Coins in copper or silver are not converted ("I set two coppers on the step" paid nothing); the
  economy counts gold. Stell's call whether to add a conversion.
- Past tense turns (C9) and scene drift (C10: a stall gains a keeper, a window becomes a well).
- Invented memories stay the largest open class ("You've seen him before", "You remember the
  warnings from the dockworkers"); the batch 6 review keeps true memories as a look's payoff, so
  a pattern cannot cut them. The outcome reader in prompt-review-2026-10-14.md is the candidate.

- Continued work that fills the pack records nothing when the draft's grant is vague ("Salvage").
- A person left behind turns up at the destination (Verity "nods approvingly from where she
  stands nearby" on the flats).

## Next

2026-10-18: the quest parser split below is done (app/quest_offers.py; CHANGELOG [Unreleased]).
The engine finds the offer line and its speaker, one small ask fills the card from that line,
a second checks it against the passage, and the engine keeps giver, duplicates and acceptance.
Replayed over the 360 archived turns the old parser was called on: the wrong jobs (the player's
own words, debt talk, bare marks) reach no model or are dropped in code; the real offers are
found. The check opponent (#89) now comes from the engine's scene record. Next run: 8B from run
142 on this code, watching `quest_fill` / `quest_check` in the traces for the fill saying yes to
no work and the check saying no to a real offer.

Paused at run 141 (2026-10-17, Stell). Before more runs: Stell's rule that a task the model keeps
failing should be made simpler (CLAUDE.md). The quest parser is that task: it reads a whole turn
and must decide offer, giver, steps, takes and duplicates at once, and a rule was added after it
almost every run. Split it into smaller asks (did someone offer work, in which line; what is the
task) and let the engine decide giver, duplicates and takes.

Earlier: run 113 on 75cdb85 or later, toward the 100-turn goal. Stock lines repeat across turns too
("You're late" from the tallyman in most runs, NPCs echoing the player's question back), alongside
the prose classes above. No clean run yet: about one state fault per run, found in T1-T7. The
prose classes above (inner life and acts for the player, past tense, scene drift) are in every
run and cannot reach zero without the outcome-reader decision in
docs/showcase/prompt-review-2026-10-14.md, which is Stell's call.
