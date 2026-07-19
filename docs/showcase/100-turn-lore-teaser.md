# Mosswake Road — 100-turn lore teaser

> Dual-role stress run: **Player** chooses actions, **GM** narrates and mutates state, Mørkyn `apply_turn` / SQLite is the only backend. No local LLM was required for this harness.

## Run snapshot

| | |
| --- | --- |
| Turns completed | **100** / 100 |
| Errors | **0** |
| Wall time | **4.889s** |
| Mean apply | **45.16 ms** / turn |
| Unique locations | 5 |
| Final location | Outer Clearing |
| Final level / XP | 1 / 135 |
| Inventory items | 6 |
| Events tracked | 7 |

## Premise

You are the **Ashen Courier** — road-worn, letter-bound, debt-haunted. The sealed letter must reach its mark. Mosswake Gate and the north road do not care if you fail.

### Opening

```
Mosswake Gate wakes under a thin frontier sky. Damp stone holds the night's cold, and cart ruts shine where lantern smoke still clings. Ashen Courier stands just inside the gate with a satchel that never quite sits light: a sealed letter presses against older cloth, and older debts press harder than the leather.

Market voices rise and fall without offering safety. A warden's gaze tracks satchels 
```

## Places that hardened into lore

- **Ashcut Alley**
- **Mosswake Gate**
- **Outer Clearing**
- **Quiet Yard**
- **River Toll Shed**

## Selected beats (player · GM)

Excerpts from the long road — not every turn, just the spine of the story.

### Turn 1 — `survey` @ Mosswake Gate

**Player:** I survey Mosswake Gate, note exits, cover, and watchers.

```
You survey Mosswake Gate with courier patience. Exits resolve first: the gate road, the market lane, a darker alley that holds smoke and boot-scrape. Cover is imperfect—crates, a cart wheel, a doorway recess—but better than open mud.

Watchers exist. One is obvious (Eldrin or som
```

### Turn 10 — `work` @ Quiet Yard

**Player:** I look for courier work: messages, package runs, or quiet deliveries.

```
You look for courier work in Quiet Yard: short runs, sealed tags, quiet packages. One offer is honest. One is bait. You can tell them apart by who avoids looking at your satchel.

You take a small legitimate run that pays poorly and costs little trust. Better than standing still 
```

### Turn 20 — `shift` @ Outer Clearing

**Player:** I move if the scene has gone cold, or dig one layer deeper if it has not.

```
The scene at Mosswake Gate cools or thickens—either way, standing still pays poorly. You shift pressure toward Outer Clearing.

Cycle 1 of the long road continues. The letter is still sealed. The debts are still patient. You are still moving.
```

### Turn 35 — `use_item` @ Mosswake Gate

**Player:** I use what gear I have carefully to stay fed or unnoticed.

```
You use what you have without ceremony: a ration if hungry, a strap if the satchel slips, shadow if eyes linger too long on Mosswake Gate.

Gear is a sentence written in advance. You read it carefully.
```

### Turn 50 — `work` @ Quiet Yard

**Player:** I look for courier work: messages, package runs, or quiet deliveries.

```
You look for courier work in Quiet Yard: short runs, sealed tags, quiet packages. One offer is honest. One is bait. You can tell them apart by who avoids looking at your satchel.

You take a small legitimate run that pays poorly and costs little trust. Better than standing still 
```

### Turn 65 — `listen` @ Outer Clearing

**Player:** I listen for talk of bandits, debt collectors, or sealed letters.

```
You listen without standing like a listener. In Outer Clearing, talk drifts: sealed packets, unpaid favors, a name spoken once and then not again.

Someone mentions Tov the Runner in the same breath as debt. That is not proof. It is a direction.
```

### Turn 80 — `shift` @ River Toll Shed

**Player:** I move if the scene has gone cold, or dig one layer deeper if it has not.

```
The scene at Mosswake Gate cools or thickens—either way, standing still pays poorly. You shift pressure toward River Toll Shed.

Cycle 4 of the long road continues. The letter is still sealed. The debts are still patient. You are still moving.
```

### Turn 100 — `shift` @ Outer Clearing

**Player:** I move if the scene has gone cold, or dig one layer deeper if it has not.

```
The scene at Mosswake Gate cools or thickens—either way, standing still pays poorly. You shift pressure toward Outer Clearing.

Cycle 5 of the long road continues. The letter is still sealed. The debts are still patient. You are still moving.
```

## What this proves

- SQLite world state survives a **100-turn** dual-role campaign without soft-resetting the premise.
- Locations, inventory, events, XP, and travel accumulate into a **coherent courier legend**.
- The harness is fast enough to re-run on every release (`python benchmarks/run_dual_role_playtest.py`).

Raw machine reports stay local under `benchmarks/reports/` (gitignored). This teaser is the shareable presentation slice.

_Generated 2026-07-19T22:05:29 · backend `apply_turn/SQLite`._
