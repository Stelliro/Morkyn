# Prompt review: what to hand to the engine and to smaller calls (2026-10-14)

Measured on 293 turns of 7B runs 4-43 (Qwen2.5 7B, 24k context; traces archived at
`D:\STELLIROS_WORKSHOP\Morkyn-playtest-archive\2026-10-14-7b-runs\`). Re-measure on Qwen3 8B first:
testing covers both models, 8B first (Stell, 2026-10-14). Nothing below is implemented yet.

## Where the time and tokens go

| Call | Calls | Avg prompt | Avg time | Job |
|---|---|---|---|---|
| Narrator draft (`draft_dsl`) | 293 | 31k chars (~8k tokens) | 8.0 s | prose plus ~30 op types |
| Verifier (`verify`) | 260 | 38k chars (~10k tokens) | 5.0 s | 245 pass (94%), 15 revise |
| Quest reader (`quest_parser`) | 146 | 4.6k chars | 5.5 s | new jobs and progress |
| Narration retries | 31 | 28k chars | 6 s | prose too short |

## Findings

1. The verifier carries the narrator's whole 19k system prompt again (for prompt caching) plus 5k
   of its own rules, the world state and the draft. It passes 94% of drafts unchanged, and two of
   its revises caused faults (run 35: single-quoted rewrite hid invented player lines; run 30: its
   patch kept the contradiction it named). The engine already re-checks most of its list.
   Skip threshold: `DEFAULT_VERIFY_SKIP_CERTAINTY` / `AI_RPG_VERIFY_SKIP_CERTAINTY` in app/llm.py.
2. The narrator keeps books the engine redoes or ignores. Ops written across 291 drafts: QUEST 12,
   QUEST_DONE 1 (the quest reader owns jobs); MOVE/WALK ~70 (the engine decides moves; the movement
   section of the prompt is ~2.5k chars); GOLD 9 and GRANT 88 with 29 grants refused (the engine
   re-settles from prose); FOCUS/GOAL/SCENE/SUMMARY/GM/TALK nearly every turn (deterministic planner
   and the engine's own turn summary exist).
3. Rules repeat in the narrator prompt: "don't act/speak/decide for the player" four times, the
   menu ban three times, second person twice.
4. Conditional rules are always sent: the user prompt's ~5k `instruction` block of "when X is
   present" rules, and the death/recovery/naming/recall paragraphs, ship on turns without those keys.
5. The ~35 phrase-level regex rules added in runs 30-43 all try to recover one fact from the final
   prose (who handed what to whom, where the player ended, who is present): one class, answered by
   many regexes.

## Recommendations (suggested order: 3, 4, 1, 2)

1. Replace the verifier with an outcome reader: one small call (~3-4k prompt) over the final, cut
   prose returning fixed JSON (place the player ends in, people present with name and role, items
   handed to or taken by the player, coin received or paid with any stated amount, injury shown).
   The engine sets state from it plus its own rules. This is the class-level fix for "state needs
   prose evidence" and should replace most phrase rules.
2. Prose-first narrator: keep NPC_NEW, GRANT, TAKE, GOLD, REL, EVENT as optional short hints; drop
   QUEST/QUEST_DONE, MOVE/WALK, SCENE, FOCUS, GOAL, SUMMARY, GM, CAST, INDEX, JOURNAL, NOTE, CLAIM,
   KARMA, SKILL and their rules. Estimate: system prompt ~19k -> ~8-9k chars.
3. Send only the rules that apply: add each conditional sentence only when its key is present.
   Usually removes ~4k of the 5k instruction block. Engine-only change.
4. State each rule once: one short section each for agency, menus and point of view.
5. Keep the quest reader as its own small call; feed it the outcome reader's facts.

Each step behind a setting, replayed over the saved runs before it becomes the default.
