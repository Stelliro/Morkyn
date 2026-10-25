"""The player's purse, held as one number of base units (m1, Stell 2026-10-24/25).

The world's currency set (app/currency.py) says what a unit is: a copper in the
coin set (1 silver = 100, 1 gold = 10,000), a credit, a cap. ``player.purse_units``
is the purse; ``player.gold`` is kept as a derived mirror in whole legacy gold
(``currency.to_legacy_gold``) for the readers that still use it (titles, local
intel, older tests and tools).

A turn carries two money keys on ``result["player"]``:

* ``gold_delta``: the legacy gold scale, what the model's GOLD op and the band
  dice speak in (whole numbers). Converted with ``currency.from_legacy_gold``.
* ``money_delta``: exact base units, written by the engine when it knows the
  sum (a price stated in silver, a ``$<number>`` command). It stands only while
  it still agrees with ``gold_delta`` (``to_legacy_gold(money_delta) ==
  gold_delta``); every engine write of ``gold_delta`` goes through
  ``put_gold`` / ``drop_gold`` here, which keep the two together.

A writer that still sets ``player.gold`` directly (an old save, a tool, a test)
is adopted: the difference between ``gold`` and the mirror of ``purse_units`` is
added in units, so nothing is lost and nothing runs twice.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app import currency

# The purse's own bounds, in legacy gold (the clamp _apply_player always had).
PURSE_MAX_GOLD = 1_000_000
TURN_GAIN_MAX_GOLD = 5_000
TURN_LOSS_MAX_GOLD = 50_000


def active_set(conn) -> dict[str, Any]:
    return currency.active_set(conn)


def _row_value(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def units_of_row(row: Any, cset: dict[str, Any]) -> int:
    """The purse a player row holds: purse_units, plus any gold a legacy writer set beside it."""
    if row is None:
        return 0
    units = int(_row_value(row, "purse_units") or 0)
    gold = int(_row_value(row, "gold") or 0)
    mirror = currency.to_legacy_gold(units, cset)
    if gold != mirror:
        units += currency.from_legacy_gold(gold - mirror, cset)
    return max(0, units)


def purse_units(conn, cset: dict[str, Any] | None = None) -> int:
    cset = cset or currency.active_set(conn)
    try:
        row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
    except Exception:
        return 0
    return units_of_row(row, cset)


def clamp_purse(units: int, cset: dict[str, Any]) -> int:
    return max(0, min(currency.from_legacy_gold(PURSE_MAX_GOLD, cset), int(units)))


def write_purse(conn, units: int, cset: dict[str, Any] | None = None) -> int:
    """Set the purse to ``units`` (clamped), with the gold mirror. Returns what was written."""
    cset = cset or currency.active_set(conn)
    units = clamp_purse(units, cset)
    conn.execute(
        "UPDATE player SET purse_units = ?, gold = ? WHERE id = 1",
        (units, currency.to_legacy_gold(units, cset)),
    )
    return units


def add_units(conn, delta: int, cset: dict[str, Any] | None = None) -> int:
    """Add ``delta`` units to the purse (clamped at 0 and the cap). Returns the new purse."""
    cset = cset or currency.active_set(conn)
    return write_purse(conn, purse_units(conn, cset) + int(delta), cset)


def add_gold(conn, gold: int | float, cset: dict[str, Any] | None = None) -> int:
    """Add an amount in legacy gold (a quest reward, a bribe): converted to units first."""
    cset = cset or currency.active_set(conn)
    return add_units(conn, currency.from_legacy_gold(gold, cset), cset)


# ---------------------------------------------------------------------------
# The turn's money keys
# ---------------------------------------------------------------------------


def _whole(value: Any) -> int | None:
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if not number.is_finite():
        return None
    return int(number) if number == number.to_integral_value() else None


def turn_units(player: dict[str, Any] | None, cset: dict[str, Any]) -> int:
    """The units this turn's player patch moves: money_delta while it agrees with gold_delta, else gold_delta converted."""
    if not isinstance(player, dict):
        return 0
    try:
        gold = int(float(player.get("gold_delta") or 0))
    except (TypeError, ValueError):
        gold = 0
    if "money_delta" in player:
        try:
            units = int(player.get("money_delta") or 0)
        except (TypeError, ValueError):
            units = None
        if units is not None and currency.to_legacy_gold(units, cset) == gold:
            return units
    try:
        return currency.from_legacy_gold(float(player.get("gold_delta") or 0), cset)
    except (TypeError, ValueError):
        return 0


def put_money(player: dict[str, Any], units: int, cset: dict[str, Any]) -> None:
    """Exact units for the turn, with gold_delta as their whole legacy gold."""
    units = int(units)
    player["money_delta"] = units
    player["gold_delta"] = currency.to_legacy_gold(units, cset)


def put_gold(player: dict[str, Any], value: Any, cset: dict[str, Any] | None = None) -> None:
    """Write gold_delta. A whole number is legacy gold as before (money_delta goes); a fraction
    ("five silver" read as 0.05 gold) is converted to exact units."""
    whole = _whole(value)
    if whole is not None:
        player["gold_delta"] = whole
        player.pop("money_delta", None)
        return
    cset = cset or currency.current_set()
    try:
        units = currency.from_legacy_gold(float(value), cset)
    except (TypeError, ValueError):
        player["gold_delta"] = 0
        player.pop("money_delta", None)
        return
    put_money(player, units, cset)


def drop_gold(player: dict[str, Any]) -> None:
    player.pop("gold_delta", None)
    player.pop("money_delta", None)


def legacy_value(units: int, cset: dict[str, Any]) -> int | float:
    """Units on the legacy gold scale, a whole number when it is one: 500 copper -> 0.05."""
    per = max(1, int(cset.get("per_legacy_gold") or 1))
    units = int(units)
    if units % per == 0:
        return units // per
    return float(Decimal(units) / Decimal(per))
