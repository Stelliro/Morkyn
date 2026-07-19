# Character portrait (design)

Status: **planned** — UI shell on setup → Character (`#characterPortraitCard`). No generator yet.

## Goals

- Show a **stable character image** derived from setup traits.
- Default: **8-bit / stylized sprite sheet** (matches map art).
- Optional upgrade: richer illustration via local/cloud image model.
- **Drift over time** after major story beats (scar, new cloak, rank change) without full random re-roll.

## Inputs (prompt / seed features)

From setup + live state:

- Name, known-as, title  
- Age/sex presentation, backstory mode  
- World style + tone  
- Equipment summary (equipped slots)  
- Last N “portrait-worthy” facts (injury, transformation, reputation)

Build a **canonical feature hash**:

```text
portrait_seed = hash(campaign_id + player_code + base_traits)
portrait_revision = count of accepted visual deltas
```

## Pipeline (v1)

1. **Template pick** — body archetype from tags (humanoid default).
2. **Palette** — from UI theme or world style.
3. **Layer stack (8-bit)** — body → clothes → hair → eyes → accessory (canvas or pre-made tiles).
4. **Optional LLM image** — only if user enables “illustrated” quality and a provider is configured.
5. **Cache** — `data/portraits/{campaign}/{revision}.png` + JSON meta.

## Evolution rules

Do **not** regenerate from scratch every turn.

| Trigger | Delta example |
| --- | --- |
| Equip unique item | Add accessory layer |
| Major injury fact | Scar / bandage layer |
| Title/reputation change | Cloak / badge color |
| Time skip years | Age palette shift |

Store deltas as ordered ops; re-render from base + ops.

## API sketch

```text
GET  /api/portrait
POST /api/portrait/regen     { "quality": "8bit"|"hi" }
POST /api/portrait/delta     { "reason": "scar", "note": "..." }  # system/internal
```

## UI

- Setup: preview frame (stub).
- Play: Player pane thumbnail; click for larger view + revision history.

## Difficulty notes

Image models are slow/noisy; **layered 8-bit** should ship first so play never blocks on portraits. LLM images are an upgrade path, not the default dependency.
