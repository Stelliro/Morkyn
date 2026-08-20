# Venues

Shops, inns, forges and temples as real places the player can be inside.

## What was wrong

A live probe (`tools/playtest_venues.py`) walked into an apothecary on a square,
asked the keeper about remedies, stepped out, and went back in. The database
recorded **one location and zero movement** for all four turns. The shop existed
only as prose.

Then the player walked two locations away and said "head all the way back to that
apothecary". The turn minted a **brand-new top-level location** called
`Apothecary` — a sibling of the square, not attached to it — and put the player
inside it in one move, at night. The keeper was Jethook (a man) on the first
visit, "a woman with a kind face" on the second, and "a man in worn clothes" on
the third, because nobody was bound to the shop.

There was no containment, no clock check, and no notion that a hamlet should not
contain an apothecary at all.

## The model

A venue is an ordinary row in `locations`, with five added columns:

| Column | Meaning |
| --- | --- |
| `parent_id` | The place you must be standing in to enter this one. `0` = an open-world place. |
| `kind` | `apothecary`, `smithy`, `inn`… `''` for open places. Supplies hours and plausibility. |
| `open_minute` / `close_minute` | Minutes past midnight. `-1`/`-1` = never closes. `close < open` wraps past midnight. |
| `settlement_size` | `hamlet` / `village` / `town` / `city`, on settlements. Inferred when blank. |
| `keeper_npc_id` | The one NPC always behind this counter. |

Keeping venues inside `locations` rather than a separate table means movement,
visit counts, entity codes, the map and export/import all keep working unchanged
— entering a shop is an ordinary move.

`app/venues.py` owns the vocabulary: kind classification from a name, the
settlement tier each kind needs, how many of a kind one settlement supports,
default hours, and the wrap-aware `is_open`.

## The four rules

**Containment.** A venue is entered from its parent. `gate_venue_move()` runs at
the single point where a move is applied, so every path (model-supplied, repaired,
DSL) goes through it. Entering from anywhere else **redirects the move to the
parent** — the journey still happens, and going inside costs the next turn. This
is what stops teleporting into an interior from across the map.

**Opening hours.** Checked against the world clock (`world_minute` in `pacing`).
A closed venue leaves the player where they are and journals `venue_closed` with
the hours. Times wrap: a tavern open `11:00-02:00` is open at 01:00 and shut at
03:00.

**Commonality.** `venue_plausibility()` refuses a venue the settlement cannot
support — a hamlet has no apothecary, a town has no counting house — and caps how
many of a kind one settlement holds (two apothecaries, four taverns). A refused
venue is never created; `_upsert_location` returns the parent instead, so the
player simply finds no such shop.

**Keeper identity.** `bind_venue_keeper()` pins the first real NPC in a venue to
`keeper_npc_id` and never reassigns it. The keeper's name and role ride in the
turn packet with an explicit instruction not to introduce a different one.

## A doorway is a move the model will not record

Containment on the server was not enough. With venues fully working underneath,
a scripted probe still produced **one location and no movement**: the model
narrated stepping inside, talking to the keeper, stepping out and going back in,
and emitted no `MOVE` for any of it. Adding prompt guidance did not fix it
either. This is the same failure class as the original travel work — the model
describes state changes instead of recording them — and it needs the same
deterministic answer.

`venue_move_intent()` classifies a line as `enter`, `exit` or neither, and
`resolve_movement()` gained four rules:

| Rule | Fires when |
| --- | --- |
| `venue_enter` | The player's line names a venue standing here — by its proper name, or just by trade ("back inside the apothecary"). |
| `venue_exit` | The player is inside a venue and the line reads as going out. |
| `venue_opened` | The player asked to walk into a kind of venue this settlement supports and none exists yet. |
| `venue_return` | The player names a venue from somewhere else. The move aims at the shop; the entry gate lands them at its door. |

Only the player's own words can open a venue. Letting the narration mint them
would drop a shop wherever the prose happened to drift.

**Detection is phrase-level on purpose.** Adding `in` and `out` to the travel
keyword set turned "I put the coin in my pocket" and "I hand out the flyers" into
travel turns. The phrase form scores 12/12 on those cases with no false positives.

## What the model is told

`movement_contract()` carries `venues_here` (name, kind, and an open/closed line
per venue), `closed_now`, and a `venue_rule`. When the player is inside a venue it
also carries `inside_venue` with the way out and the bound keeper.

Interiors are deliberately **excluded from `known_places`** — listing them
alongside travel destinations invited the model to "travel" straight into a shop
from across the map, which is exactly what containment forbids.

## Traps

- **Do not write from `settlement_size_for()`.** It runs from `get_state`, a read
  path; persisting the inferred size there opened a write inside another
  transaction and deadlocked the database (the whole suite went from 3s to 25s
  and four tests failed with "database is locked"). The inference is
  deterministic, so caching it buys nothing.
- **Venues do not nest.** A shop named while the player is already inside a shop
  belongs to the street outside, not to the shop. `_venue_parent_for_new_place()`
  walks up to the parent.
- **Possessive trade names are not shops.** "The Alchemist's Rest" and "The
  Smith's Arms" are inns borrowing a trade word; "Baker's Row" is a street.
  Classification deliberately ignores possessives, because an unrecognised venue
  behaves like an ordinary place — a much cheaper mistake than turning an inn
  into an alchemist.

## Testing

`tests/test_venues.py` (38 tests) covers classification, wrap-around hours,
commonality by settlement size, containment and no-nesting, all four gate
outcomes, capacity, keeper stability, doorway detection and its false-positive
guard, the three repair rules, what the state and contract expose, and the
migration of a pre-venue database.

`tools/playtest_venues.py` runs the original scripted probe against a live model:
enter a shop from the square, act inside, step out, re-enter, leave town, travel,
return from a distance, and try the door after hours.

`tools/make_debug_save.py` builds a world with three venues on one square
(apothecary, smithy, inn), each with a bound keeper, so all of this is testable
without a model call.
