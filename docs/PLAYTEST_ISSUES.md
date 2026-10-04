# Playtest issues (0.10 stabilisation)

Issues the player reports during a test session, logged as they come in and
fixed together once the player calls testing done. Newest last.

Each entry: what the player saw, the turn or screen, the trace or save if one
points at it, and a first guess at the cause (not acted on until testing ends).

| # | Reported | Where | What the player saw | Evidence | First guess at cause | Status |
|---|---|---|---|---|---|---|
| 1 | 2026-10-05 | New game > Custom Proficiencies (randomize) | Random fill gave twelve poetic verb phrases ("weave light, master the dance of shadows, earn trust through deeds, ... braid destiny") instead of what the field asks for: proficiency names plus training-rule phrases (seed skill name, tracking style, hard limits). | Field help text vs. output. The randomize ask for custom_skills (llm.py ~6791 optimize note, ~6350 intent rule) only says 'comma-separated skill discovery, training limits, progression rules, or named proficiencies'; evaluate_custom_skills_quality (llm.py:5802) only checks seed/frame shape for one-skill or OP-MC intents, so a normal preset passes anything non-empty. | The ask doesn't spell out the shape (name: rule, tracking, limit) the help text promises, so the model writes flavour slogans. Player's idea: let the engine and the model settle proficiencies in the post-start generation phase, before turn 1. | Open |
