# Saltmarrow on Qwen3 8B: findings (2026-10-15)

Same setup as the 7B runs (docs/showcase/saltmarrow-setup.json), Qwen3 8B Q4_K_M
(`D:\morkyn-stage-models\Qwen3-8B-Q4_K_M.gguf`) as the GM through MLE, Claude as the player.
Testing order (Stell): 8B until no issues, then the 7B. Mode: play long, log faults by class
(`D:\STELLIROS_WORKSHOP\Morkyn-playtest-archive\2026-10-14-8b-runs\classes.md`), fix each class at
the one place it is decided, replay every saved 7B and 8B turn before committing.

Every fix below has a test and passed the full suite with only the 15 known failures (the
dice-audit flake tripped twice and passed alone). Nothing is pushed.

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

## Logged, not fixed

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

Run 38 on 1ba5b53 or later; keep logging by class.
