# Playtest issues (0.10 stabilisation)

Issues the player reports during a test session, logged as they come in and
fixed together once the player calls testing done. Newest last.

Each entry: what the player saw, the turn or screen, the trace or save if one
points at it, and a first guess at the cause (not acted on until testing ends).

| # | Reported | Where | What the player saw | Evidence | First guess at cause | Status |
|---|---|---|---|---|---|---|
| 1 | 2026-10-05 | New game > Custom Proficiencies (randomize) | Random fill gave twelve poetic verb phrases ("weave light, master the dance of shadows, earn trust through deeds, ... braid destiny") instead of what the field asks for: proficiency names plus training-rule phrases (seed skill name, tracking style, hard limits). | Field help text vs. output. The randomize ask for custom_skills (llm.py ~6791 optimize note, ~6350 intent rule) only says 'comma-separated skill discovery, training limits, progression rules, or named proficiencies'; evaluate_custom_skills_quality (llm.py:5802) only checks seed/frame shape for one-skill or OP-MC intents, so a normal preset passes anything non-empty. | The ask doesn't spell out the shape (name: rule, tracking, limit) the help text promises, so the model writes flavour slogans. Player's idea: let the engine and the model settle proficiencies in the post-start generation phase, before turn 1. | Open |
| 2 | 2026-10-05 | New game > Presets (saved presets list) | (a) Saved presets are hard to rename. (b) Saved "overpowered", then saved another: both show the exact same name in the list. Wanted: duplicates numbered with the lowest free number (first has no number, next is 1, then 2...); deleting one frees its number for the next save, so no 1,2,3,15,17 gaps. | static/app.js: saveSelectedPresetFromEditor (~5353) and createUserPreset (~5255) push the typed label as-is with a new id; no uniqueness check against loadUserPresets(). Only built-in collisions get " copy". Rename is only via #presetLabelInput (persistUserPresetText on input, ~5292), inside the preset editor. | (a) Rename has no obvious control; the label box sits in the editor fold. (b) No name de-duplication on save; needs a lowest-free-suffix helper used by save, new and rename. | Open |
