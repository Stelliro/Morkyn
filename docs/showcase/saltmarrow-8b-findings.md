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

## Logged, not fixed

- C9 voice: a turn in past tense (r2 T3); NPC lines without quote marks (r4 T4).
- C10 model continuity: people renamed or swapped mid-scene (the shadow man Gregory -> Osric),
  stock dodges ("You're not here for the tide, are you?") instead of answers, scene drift.
- Invented memories of the player's past: a pattern cannot tell them from true backstory; candidate
  for the outcome reader in docs/showcase/prompt-review-2026-10-14.md.
- #88: persuasion still rolls on plain questions (Stell's call).

## Next

Run 6 on 0099f7a or later; keep logging by class.
