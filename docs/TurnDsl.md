# TurnDsl — NAR+OPS draft language

## Purpose

Local models are unreliable at large free-form turn JSON. Mørkyn drafts turns as a **fixed text form**:

```text
===NAR===
continuous playable prose with [[entity codes]]

===OPS===
SUMMARY merchant warned about bandits near L1
TALK A "trouble on the roads"
GRANT "travel ration" QTY 1 TYPE food
```

A **deterministic transcoder** (`app/turn_dsl.py`) maps opcodes into the turn dict that `apply_turn` already expects. The model does **not** write storage escapes or application code.

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `AI_RPG_DRAFT_MODE` | `dsl` | `dsl` / `ops` / `on` = NAR+OPS first; `json` = legacy JSON draft only |
| `AI_RPG_DSL_SKIP_VERIFY` | `0` | If `1`, skip model verifier after a successful DSL draft |
| `OLLAMA_THINK` | `0` | Keep off for Qwen3 so `message.content` is filled |

On DSL parse failure, the pipeline falls back to the legacy JSON draft path.

## Escape policy

- Models write **raw Unicode** inside `"quoted"` op args.
- `encode_storage_text` / `decode_storage_text` percent-encode for durable storage when needed.
- The model must not invent `%XX` or HTML entities; decoding is transcoder-owned.

## Closed opcodes (v0)

`SUMMARY`, `SCENE`, `GOAL`, `FOCUS`, `NPC_NEW`, `NPC_NOTE`, `TALK`, `GRANT`, `TAKE`, `GOLD`, `XP`, `HP`, `KARMA`, `MOVE`, `LOC_NEW`, `EVENT`, `GM`, `REL`, `SKILL`, `CLAIM`, `JOURNAL`, `INDEX`, `NOTE`.

Unknown opcodes raise `TurnDslError` (fail loud).

## Pipeline

1. Context steward / handoff cleanup  
2. DSL draft (`draft_dsl` plain-text call)  
3. Parse + transcoder → turn JSON  
4. Certainty policy; optional model verify  
5. `apply_turn`  

## Files

- `app/turn_dsl.py` — opcodes, parser, transcoder, DSL system prompt  
- `app/llm.py` — `_chat_text`, `_try_dsl_draft`, `generate_turn` wiring  
