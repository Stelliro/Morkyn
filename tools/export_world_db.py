"""Export a Mørkyn world database to readable files, read-only.

    python tools/export_world_db.py <world.db> --out <dir> [--full] [--label NAME]

Writes two files into --out:

- ``<label>.json``: every table with its columns, row count and rows. Long
  text cells (map grids, turn snapshots, prompts) are cut to 4,000 characters
  with a marker unless --full is given; binary cells are listed by size.
- ``<label>.md``: a short readable view of the tables a reader cares about
  (player, places, people, items, quests, dice, journal), plus every table's
  row count.

The database is opened with ``mode=ro``: this never writes to a save.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

CELL_LIMIT = 4000

# The tables the Markdown view shows, with the columns worth reading.
VIEW = [
    ("player", ["name", "level", "xp", "gold", "health", "max_health", "energy", "max_energy", "current_location_id"]),
    ("locations", ["id", "code", "name", "kind"]),
    ("npcs", ["code", "name", "role", "location_id", "attitude", "trust", "knows_player_name"]),
    ("inventory", ["name", "quantity", "item_type", "rarity", "equipped_slot"]),
    ("abilities", ["name", "rank", "locked", "cost", "power_type"]),
    ("player_skills", ["name", "rank", "xp"]),
    ("quests", ["code", "title", "status", "current_step", "total_steps", "reward_gold", "reward_xp"]),
    ("quest_steps", ["quest_id", "step_number", "title", "status"]),
    ("npc_player_relationships", ["npc_id", "affinity", "fear", "respect"]),
    ("dice_rolls", ["turn", "tag", "kind", "band", "notation", "value", "source"]),
]
JOURNAL_KINDS_SKIPPED = {"narration", "player"}


def _cell(value: Any, full: bool) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    if isinstance(value, str) and not full and len(value) > CELL_LIMIT:
        return value[:CELL_LIMIT] + f" ... <cut, {len(value)} chars>"
    return value


def export(db_path: Path, full: bool = False) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        out: dict[str, Any] = {
            # The file name only: a full path would publish the exporter's folders.
            "database": db_path.name,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "full": full,
            "tables": {},
        }
        for table in tables:
            columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            rows = [{k: _cell(row[k], full) for k in row.keys()} for row in conn.execute(f'SELECT * FROM "{table}"')]
            out["tables"][table] = {"columns": columns, "count": len(rows), "rows": rows}
        return out
    finally:
        conn.close()


def _md_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    cols = [c for c in columns if rows and c in rows[0]]
    if not rows or not cols:
        return ["_none_", ""]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in rows:
        cells = [str(row.get(c) if row.get(c) is not None else "").replace("|", "/").replace("\n", " ")[:120] for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def markdown(data: dict[str, Any], label: str) -> str:
    tables = data["tables"]
    lines = [f"# World database: {label}", "", f"Exported {data['exported_at']} from `{Path(data['database']).name}` (read-only).", ""]
    for table, columns in VIEW:
        if table not in tables:
            continue
        lines += [f"## {table} ({tables[table]['count']})", ""]
        lines += _md_table(tables[table]["rows"], columns)
    if "journal" in tables:
        rows = [r for r in tables["journal"]["rows"] if r.get("kind") not in JOURNAL_KINDS_SKIPPED]
        lines += [f"## journal, engine entries ({len(rows)} of {tables['journal']['count']})", ""]
        lines += [f"- T{r.get('turn')} `{r.get('kind')}` {str(r.get('content') or '').replace(chr(10), ' ')[:300]}" for r in rows]
        lines.append("")
    lines += ["## Row counts", "", "| table | rows |", "| --- | --- |"]
    lines += [f"| {t} | {v['count']} |" for t, v in tables.items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--full", action="store_true", help="keep long text cells whole")
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"no database at {args.db}", file=sys.stderr)
        return 2
    label = args.label or args.db.stem
    data = export(args.db, full=args.full)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{label}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (args.out / f"{label}.md").write_text(markdown(data, label), encoding="utf-8")
    print(f"{label}: {len(data['tables'])} tables, {sum(t['count'] for t in data['tables'].values())} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
