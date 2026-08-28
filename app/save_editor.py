"""
Read and edit the contents of a campaign save.

There was no way to do this. Of 79 mutating endpoints, none touched a save's
contents: the closest were ``/api/import`` (the whole world, all or nothing) and
save / load / delete. Changing one item's quantity meant finding
``data/campaign_slots/<slot>/world.json``, learning its shape, parsing five
megabytes of JSON, editing the row by hand and writing it back -- and since the
blob store landed, understanding ``{"__blob__": ...}`` references as well.

One module serves both audiences deliberately. The browser save editor and an
agent driving the HTTP API run the same code, so neither can be right while the
other is wrong.

Two tables are not editable. ``world_maps`` is generated tile data and
``settings`` holds base64 character art; between them they are 99% of a save's
bytes, nobody edits them by hand on purpose, and a malformed edit to either
breaks the map or the portraits with no useful error. Everything a person
actually wants to fix -- inventory, player, skills, abilities, NPCs, locations,
journal -- is about 25 KB and fully editable.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.world import (
    campaign_slots_dir,
    externalise_blobs,
    internalise_blobs,
    _safe_slot_name,
)

# Generated payloads, not records anyone edits by hand.
BLOCKED_TABLES = frozenset({"world_maps", "settings"})
MAX_EDITS = 200
SCALAR_TYPES = (str, int, float, bool, type(None))


class SaveEditError(ValueError):
    """A refused edit. The message is written to be shown to whoever asked."""


def _slot_dir(slot: str) -> Path:
    return campaign_slots_dir() / _safe_slot_name(slot)


def _read_world(slot: str) -> tuple[dict[str, Any], Path]:
    safe = _safe_slot_name(slot)
    path = _slot_dir(safe) / "world.json"
    if not path.exists():
        raise SaveEditError(f"Save '{safe}' was not found.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveEditError(f"Save '{safe}' could not be read: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        raise SaveEditError(f"Save '{safe}' is not a world export.")
    return internalise_blobs(data, safe), path


def read_save(slot: str) -> dict[str, Any]:
    """
    The editable contents of a save, plus what was left out and why.

    Blocked tables are reported by name and row count rather than silently
    dropped: a caller that cannot see a table exists cannot tell the difference
    between "not editable" and "not there".
    """
    safe = _safe_slot_name(slot)
    world, _ = _read_world(safe)
    tables = world.get("tables") or {}

    editable: dict[str, Any] = {}
    blocked: list[dict[str, Any]] = []
    for name in sorted(tables):
        rows = tables.get(name)
        if name in BLOCKED_TABLES:
            blocked.append(
                {
                    "table": name,
                    "rows": len(rows) if isinstance(rows, list) else 0,
                    "reason": "generated data (map tiles, character art) — not hand-editable",
                }
            )
            continue
        editable[name] = rows

    metadata: dict[str, Any] = {}
    meta_path = _slot_dir(safe) / "metadata.json"
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}

    return {
        "slot": safe,
        "metadata": metadata,
        "tables": editable,
        "blocked": blocked,
        "columns": {name: _columns_of(rows) for name, rows in editable.items()},
    }


def _columns_of(rows: Any) -> list[str]:
    seen: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                for key in row:
                    if key not in seen:
                        seen.append(key)
    return seen


def _match(row: dict[str, Any], where: dict[str, Any]) -> bool:
    return all(str(row.get(key)) == str(value) for key, value in where.items())


def _validate_values(values: Any, what: str) -> dict[str, Any]:
    if not isinstance(values, dict) or not values:
        raise SaveEditError(f"{what} must be a non-empty object of column: value.")
    for key, value in values.items():
        if not isinstance(value, SCALAR_TYPES):
            raise SaveEditError(
                f"{what}.{key} must be a string, number, boolean or null — "
                f"got {type(value).__name__}. Nested structures are stored as JSON "
                f"strings in this format."
            )
    return dict(values)


def apply_edits(slot: str, edits: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """
    Apply a list of edits to a save.

    Each edit names a table and one of three actions::

        {"table": "inventory", "where": {"code": "I4"}, "set": {"quantity": 1}}
        {"table": "inventory", "where": {"code": "I4"}, "delete": true}
        {"table": "inventory", "insert": {"code": "I5", "name": "rope", ...}}

    All or nothing. Every edit is validated and applied to an in-memory copy
    first, and the file is only rewritten once all of them succeed -- a save
    half-edited by a typo in the fourth operation is worse than a refusal.

    ``dry_run`` reports exactly what would change and writes nothing, so a
    caller can look before it leaps.
    """
    safe = _safe_slot_name(slot)
    if not isinstance(edits, list) or not edits:
        raise SaveEditError("Provide a non-empty list of edits.")
    if len(edits) > MAX_EDITS:
        raise SaveEditError(f"Too many edits in one request (limit {MAX_EDITS}).")

    world, path = _read_world(safe)
    tables = world.get("tables") or {}
    results: list[dict[str, Any]] = []

    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise SaveEditError(f"Edit {index} is not an object.")
        table = str(edit.get("table") or "").strip()
        if not table:
            raise SaveEditError(f"Edit {index} is missing 'table'.")
        if table in BLOCKED_TABLES:
            raise SaveEditError(
                f"Edit {index}: '{table}' holds generated data (map tiles or character art) "
                f"and is not editable here."
            )
        rows = tables.get(table)
        if not isinstance(rows, list):
            known = ", ".join(sorted(k for k in tables if k not in BLOCKED_TABLES))
            raise SaveEditError(f"Edit {index}: no table '{table}' in this save. Known: {known}.")

        if edit.get("insert") is not None:
            values = _validate_values(edit.get("insert"), f"Edit {index}: insert")
            rows.append(values)
            results.append({"table": table, "action": "insert", "matched": 1, "changed": 1})
            continue

        where = edit.get("where")
        if not isinstance(where, dict) or not where:
            raise SaveEditError(
                f"Edit {index}: 'where' must be a non-empty object identifying the rows to change."
            )
        matched = [row for row in rows if isinstance(row, dict) and _match(row, where)]
        if not matched:
            raise SaveEditError(
                f"Edit {index}: nothing in '{table}' matches {json.dumps(where)}. "
                f"Nothing was changed."
            )

        if edit.get("delete"):
            for row in matched:
                rows.remove(row)
            results.append(
                {"table": table, "action": "delete", "matched": len(matched), "changed": len(matched)}
            )
            continue

        values = _validate_values(edit.get("set"), f"Edit {index}: set")
        changed = 0
        before: list[dict[str, Any]] = []
        for row in matched:
            was = {key: row.get(key) for key in values}
            if was != values:
                before.append(was)
                row.update(values)
                changed += 1
        results.append(
            {
                "table": table,
                "action": "set",
                "matched": len(matched),
                "changed": changed,
                "before": before,
                "after": values,
            }
        )

    report: dict[str, Any] = {
        "slot": safe,
        "dry_run": bool(dry_run),
        "edits": results,
        "rows_changed": sum(int(item.get("changed") or 0) for item in results),
    }
    if dry_run:
        return report

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f".json.bak-{stamp}")
    shutil.copy2(path, backup)
    path.write_text(
        json.dumps(externalise_blobs(world), ensure_ascii=True, indent=2), encoding="utf-8"
    )
    report["backup"] = backup.name
    return report
