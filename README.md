# Shadowforge AI RPG

**A local-first, consistency-focused AI RPG with durable state and agentic memory management.**

Version `0.6.0` (with major efficiency and stability upgrades)

Shadowforge is a local browser RPG powered by your own LLM. The model narrates immersive turns and proposes structured world changes. SQLite is the single source of truth. The new hierarchical memory system, dynamic token budgeting, and agentic CoD steps keep the loop stable and efficient for very long playthroughs without bloat or token limits.

## Key Features

- Local-only (llama.cpp or Ollama)
- Persistent SQLite world with entity codes, equipment effects, GM events, and source_index
- Smart context builder with intent-specific pruning and relevance scoring
- Hierarchical memory consolidation and dynamic token budget guard
- Agentic internal reasoning (Observe → Plan → Narrate → Self-check)
- UI diagnostics, compact mode toggle, off-screen NPC simulation, campaign persistence
- Rewind, regenerate, import/export, phone-friendly UI
- Rich 1000–1500 character narration with clickable entity references

## Screenshots

(Coming soon — placeholder images will be added after generation)

![Banner](https://via.placeholder.com/1200x600/1a1a2e/0f0f1f?text=Shadowforge+AI+RPG)

## Quick Start

[Same as before...]

## Why Shadowforge?

It combines the consistency and persistence of a tabletop campaign with the creativity of a local LLM — without the memory death spiral that plagues most AI RPGs. The loop is now self-stabilizing and ready for long campaigns.

## License

Non-commercial under PolyForm Noncommercial License 1.0.0.

See full details in LICENSE.md.