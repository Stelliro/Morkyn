"""
Flat tile world: presets, weighted state generation, image archive.

Model:
  - Each cell has a *state* (city, waterfall, mountain, void, …) from tile_states.
  - elevation 0/1 only: mountains/cliffs/hills use 1 and grow as multi-tile blobs.
  - Art is not baked into generation: after states are set, images are sampled
    from tile_images (searchable archive; disable forever / this run / delete).
"""
from __future__ import annotations

import json
import os
import random
import re
import time
import uuid
from pathlib import Path
from typing import Any

from app.db import connect, row_to_dict, rows_to_dicts

ROOT = Path(__file__).resolve().parent.parent
TILE_ART_DIR = ROOT / "data" / "tile_art"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def list_tile_states() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tile_states ORDER BY category, label"
        ).fetchall()
    out = []
    for row in rows:
        item = row_to_dict(row) or {}
        try:
            item["tags"] = json.loads(item.get("tags") or "[]")
        except json.JSONDecodeError:
            item["tags"] = []
        item["walkable"] = bool(item.get("walkable"))
        item["space_ok"] = bool(item.get("space_ok"))
        out.append(item)
    return out


def list_world_presets() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM world_presets ORDER BY sort_order, label"
        ).fetchall()
    out = []
    for row in rows:
        item = row_to_dict(row) or {}
        try:
            item["weights"] = json.loads(item.get("weights_json") or "{}")
        except json.JSONDecodeError:
            item["weights"] = {}
        try:
            item["features"] = json.loads(item.get("features_json") or "{}")
        except json.JSONDecodeError:
            item["features"] = {}
        item.pop("weights_json", None)
        item.pop("features_json", None)
        out.append(item)
    return out


def get_world_preset(preset_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM world_presets WHERE id = ?",
            (preset_id,),
        ).fetchone()
    if not row:
        return None
    item = row_to_dict(row) or {}
    item["weights"] = json.loads(item.get("weights_json") or "{}")
    item["features"] = json.loads(item.get("features_json") or "{}")
    item.pop("weights_json", None)
    item.pop("features_json", None)
    return item


def get_tile_state(state_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM tile_states WHERE id = ?",
            (state_id,),
        ).fetchone()
    if not row:
        return None
    item = row_to_dict(row) or {}
    item["tags"] = json.loads(item.get("tags") or "[]")
    item["walkable"] = bool(item.get("walkable"))
    item["space_ok"] = bool(item.get("space_ok"))
    return item


# ---------------------------------------------------------------------------
# Image archive
# ---------------------------------------------------------------------------

def search_tile_images(
    *,
    query: str = "",
    state_id: str = "",
    include_disabled: bool = False,
    run_id: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    limit = max(1, min(500, int(limit)))
    clauses: list[str] = []
    params: list[Any] = []
    if state_id:
        clauses.append("i.state_id = ?")
        params.append(state_id)
    if not include_disabled:
        clauses.append("i.disabled_forever = 0")
    if run_id:
        clauses.append(
            "i.id NOT IN (SELECT image_id FROM tile_image_run_disable WHERE run_id = ?)"
        )
        params.append(run_id)
    if query.strip():
        q = f"%{query.strip().lower()}%"
        clauses.append(
            "(lower(i.state_id) LIKE ? OR lower(i.tags) LIKE ? OR lower(i.prompt) LIKE ? OR lower(i.source) LIKE ?)"
        )
        params.extend([q, q, q, q])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT i.*, s.label AS state_label, s.category AS state_category
        FROM tile_images i
        LEFT JOIN tile_states s ON s.id = i.state_id
        {where}
        ORDER BY i.created_at DESC, i.id DESC
        LIMIT ?
    """
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return rows_to_dicts(rows)


def add_tile_image(
    *,
    state_id: str,
    path: str = "",
    data_url: str = "",
    source: str = "user",
    prompt: str = "",
    tags: str = "",
    quality: str = "8bit",
) -> dict[str, Any]:
    if not get_tile_state(state_id):
        raise ValueError(f"Unknown tile state: {state_id}")
    if not path and not data_url:
        raise ValueError("Provide path or data_url for the image.")
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tile_images
              (state_id, path, data_url, source, prompt, tags, quality)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state_id,
                path,
                data_url[:2_000_000] if data_url else "",  # soft cap
                source or "user",
                prompt or "",
                tags or "",
                quality or "8bit",
            ),
        )
        image_id = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM tile_images WHERE id = ?", (image_id,)).fetchone()
    return row_to_dict(row) or {}


def set_tile_images_disabled_forever(image_ids: list[int], disabled: bool = True) -> int:
    if not image_ids:
        return 0
    flag = 1 if disabled else 0
    with connect() as conn:
        for iid in image_ids:
            conn.execute(
                "UPDATE tile_images SET disabled_forever = ? WHERE id = ?",
                (flag, int(iid)),
            )
        return len(image_ids)


def disable_tile_images_for_run(image_ids: list[int], run_id: str) -> int:
    if not image_ids or not run_id:
        return 0
    with connect() as conn:
        for iid in image_ids:
            conn.execute(
                "INSERT OR IGNORE INTO tile_image_run_disable (image_id, run_id) VALUES (?, ?)",
                (int(iid), run_id),
            )
    return len(image_ids)


def clear_run_disables(run_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM tile_image_run_disable WHERE run_id = ?", (run_id,))


def delete_tile_images(image_ids: list[int], *, delete_files: bool = True) -> int:
    if not image_ids:
        return 0
    removed = 0
    with connect() as conn:
        for iid in image_ids:
            row = conn.execute(
                "SELECT path FROM tile_images WHERE id = ?",
                (int(iid),),
            ).fetchone()
            if not row:
                continue
            path = str(row["path"] or "")
            conn.execute("DELETE FROM tile_image_run_disable WHERE image_id = ?", (int(iid),))
            conn.execute("DELETE FROM tile_images WHERE id = ?", (int(iid),))
            removed += 1
            if delete_files and path:
                try:
                    full = ROOT / path if not Path(path).is_absolute() else Path(path)
                    if full.is_file() and "data" in full.parts:
                        full.unlink()
                except OSError:
                    pass
    return removed


def pick_image_for_state(state_id: str, *, run_id: str = "", rng: random.Random | None = None) -> dict[str, Any] | None:
    rng = rng or random.Random()
    candidates = search_tile_images(state_id=state_id, run_id=run_id, include_disabled=False, limit=200)
    if not candidates:
        return None
    return rng.choice(candidates)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _value_noise(width: int, height: int, rng: random.Random, scale: int = 6) -> list[list[float]]:
    gw = max(2, width // scale + 2)
    gh = max(2, height // scale + 2)
    grid = [[rng.random() for _ in range(gw)] for _ in range(gh)]

    def sample(x: float, y: float) -> float:
        x0 = int(x) % (gw - 1)
        y0 = int(y) % (gh - 1)
        x1 = x0 + 1
        y1 = y0 + 1
        fx = x - int(x)
        fy = y - int(y)
        # smoothstep
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)
        a = grid[y0][x0] * (1 - fx) + grid[y0][x1] * fx
        b = grid[y1][x0] * (1 - fx) + grid[y1][x1] * fx
        return a * (1 - fy) + b * fy

    out: list[list[float]] = []
    for y in range(height):
        row = []
        for x in range(width):
            row.append(sample(x / scale, y / scale))
        out.append(row)
    return out


def _weighted_pick(weights: dict[str, float], rng: random.Random, allowed: set[str] | None = None) -> str:
    items = []
    for k, w in weights.items():
        if allowed is not None and k not in allowed:
            continue
        try:
            ww = float(w)
        except (TypeError, ValueError):
            continue
        if ww > 0:
            items.append((k, ww))
    if not items:
        return "plains"
    total = sum(w for _, w in items)
    r = rng.random() * total
    acc = 0.0
    for k, w in items:
        acc += w
        if r <= acc:
            return k
    return items[-1][0]


def _neighbors(x: int, y: int, width: int, height: int) -> list[tuple[int, int]]:
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                out.append((nx, ny))
    return out


def _grow_blob(
    tiles: list[list[dict[str, Any]]],
    *,
    start: tuple[int, int],
    state: str,
    elevation: int,
    size: int,
    rng: random.Random,
    walkable: bool,
) -> None:
    width = len(tiles[0])
    height = len(tiles)
    frontier = [start]
    painted = 0
    seen = {start}
    while frontier and painted < size:
        x, y = frontier.pop(rng.randrange(len(frontier)))
        cell = tiles[y][x]
        # Don't overwrite pure water cores with mountain unless forced
        if cell["state"] == "water" and state == "mountain":
            pass
        cell["state"] = state
        cell["elevation"] = elevation
        cell["walkable"] = walkable
        painted += 1
        for n in _neighbors(x, y, width, height):
            if n not in seen and rng.random() < 0.72:
                seen.add(n)
                frontier.append(n)


def generate_map(
    *,
    preset_id: str = "forest_march",
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
    assign_images: bool = True,
    run_id: str | None = None,
) -> dict[str, Any]:
    preset = get_world_preset(preset_id) or get_world_preset("frontier_any")
    if not preset:
        raise ValueError("No world presets available.")
    seed = int(seed if seed is not None else (time.time_ns() % (2**31 - 1)))
    rng = random.Random(seed)
    width = int(width or preset.get("width") or 32)
    height = int(height or preset.get("height") or 32)
    width = max(8, min(96, width))
    height = max(8, min(96, height))
    weights = dict(preset.get("weights") or {})
    features = dict(preset.get("features") or {})
    is_space = bool(features.get("space")) or str(preset.get("environment") or "") in {
        "orbital",
        "deep_space",
    }
    run_id = run_id or f"map-{seed}-{uuid.uuid4().hex[:8]}"

    state_meta = {s["id"]: s for s in list_tile_states()}
    noise = _value_noise(width, height, rng, scale=5)
    moist = _value_noise(width, height, rng, scale=7)

    tiles: list[list[dict[str, Any]]] = []
    for y in range(height):
        row = []
        for x in range(width):
            n = noise[y][x]
            m = moist[y][x]
            # Bias weights slightly by noise so regions cohere
            local = dict(weights)
            if not is_space:
                if n < 0.28:
                    local["water"] = local.get("water", 5) * 3.5
                elif n > 0.78:
                    local["mountain"] = local.get("mountain", 3) * 2.8
                    local["hill"] = local.get("hill", 3) * 2.0
                if m > 0.7:
                    local["forest"] = local.get("forest", 5) * 1.6
                    local["swamp"] = local.get("swamp", 1) * 1.8
                if m < 0.25:
                    local["desert"] = local.get("desert", 1) * 2.0
                    local["ash"] = local.get("ash", 1) * 1.3
            else:
                if n < 0.35:
                    local["void"] = local.get("void", 20) * 1.4
                if n > 0.75:
                    local["asteroid"] = local.get("asteroid", 5) * 2.0
            sid = _weighted_pick(local, rng)
            meta = state_meta.get(sid) or {}
            elev = int(meta.get("elevation") or 0)
            # Flat world: only 0/1
            elev = 1 if elev >= 1 else 0
            walk = bool(meta.get("walkable", True))
            row.append(
                {
                    "x": x,
                    "y": y,
                    "state": sid,
                    "elevation": elev,
                    "walkable": walk,
                    "image_id": None,
                    "image_path": "",
                    "image_data_url": "",
                }
            )
        tiles.append(row)

    # Water bodies (terrestrial)
    if not is_space and features.get("water_bodies", 0):
        bodies = int(features.get("water_bodies") or 0)
        for _ in range(bodies):
            cx, cy = rng.randrange(width), rng.randrange(height)
            size = rng.randint(8, max(9, width * height // 40))
            _grow_blob(
                tiles,
                start=(cx, cy),
                state="water",
                elevation=0,
                size=size,
                rng=rng,
                walkable=False,
            )

    # Mountain blobs stretch across several tiles (elevation 1)
    blob_min = int(features.get("mountain_blob_min") or 0)
    blob_max = int(features.get("mountain_blob_max") or 0)
    if blob_max > 0 and "mountain" in weights:
        count = rng.randint(1, max(1, width // 10))
        for _ in range(count):
            cx, cy = rng.randrange(width), rng.randrange(height)
            size = rng.randint(max(2, blob_min), max(blob_min + 1, blob_max))
            _grow_blob(
                tiles,
                start=(cx, cy),
                state="mountain",
                elevation=1,
                size=size,
                rng=rng,
                walkable=False,
            )
            # Ring some hills / cliffs at edges of the blob
            for y in range(height):
                for x in range(width):
                    if tiles[y][x]["state"] != "mountain":
                        continue
                    for nx, ny in _neighbors(x, y, width, height):
                        if tiles[ny][nx]["state"] not in {"mountain", "cliff", "water"}:
                            if rng.random() < 0.18:
                                tiles[ny][nx]["state"] = "cliff"
                                tiles[ny][nx]["elevation"] = 1
                                tiles[ny][nx]["walkable"] = False
                            elif rng.random() < 0.25:
                                tiles[ny][nx]["state"] = "hill"
                                tiles[ny][nx]["elevation"] = 1
                                tiles[ny][nx]["walkable"] = True

    # Landmark stamps (city, monolith, waterfall, gate, …)
    landmark_pool = [
        s for s, w in weights.items()
        if w > 0 and (state_meta.get(s) or {}).get("category") in {"landmark", "settlement"}
    ]
    if not landmark_pool:
        landmark_pool = ["city", "monolith", "ruins"]
    landmark_count = int(features.get("landmark_count") or 3)
    placed: list[dict[str, Any]] = []
    for _ in range(landmark_count):
        for _attempt in range(40):
            x, y = rng.randrange(width), rng.randrange(height)
            cell = tiles[y][x]
            if cell["state"] in {"water", "void", "lava"} and rng.random() < 0.85:
                continue
            state = _weighted_pick(
                {k: float(weights.get(k, 1)) for k in landmark_pool},
                rng,
            )
            meta = state_meta.get(state) or {}
            cell["state"] = state
            cell["elevation"] = 1 if int(meta.get("elevation") or 0) >= 1 else cell["elevation"]
            cell["walkable"] = bool(meta.get("walkable", True))
            placed.append({"x": x, "y": y, "state": state})
            break

    # Cliffs along elevation transitions
    for y in range(height):
        for x in range(width):
            if tiles[y][x]["elevation"] != 1:
                continue
            for nx, ny in _neighbors(x, y, width, height):
                if tiles[ny][nx]["elevation"] == 0 and tiles[y][x]["state"] == "mountain":
                    if tiles[ny][nx]["state"] in {"plains", "forest", "desert", "ash", "beach"} and rng.random() < 0.12:
                        tiles[ny][nx]["state"] = "cliff"
                        tiles[ny][nx]["elevation"] = 1
                        tiles[ny][nx]["walkable"] = False

    # Player start: walkable non-void, prefer town/road/plains
    start = _pick_start(tiles, rng, prefer=("town", "village", "city", "road", "plains", "station", "colony"))

    # Assign images from archive
    image_hits = 0
    missing_states: set[str] = set()
    if assign_images:
        for y in range(height):
            for x in range(width):
                cell = tiles[y][x]
                img = pick_image_for_state(cell["state"], run_id=run_id, rng=rng)
                if img:
                    cell["image_id"] = img.get("id")
                    cell["image_path"] = img.get("path") or ""
                    cell["image_data_url"] = img.get("data_url") or ""
                    image_hits += 1
                else:
                    missing_states.add(cell["state"])

    flat = [cell for row in tiles for cell in row]
    map_id = run_id
    payload = {
        "id": map_id,
        "preset_id": preset["id"],
        "seed": seed,
        "width": width,
        "height": height,
        "age": preset.get("age") or "",
        "environment": preset.get("environment") or "",
        "player": {"x": start[0], "y": start[1]},
        "landmarks": placed,
        "tiles": flat,
        "grid": tiles,
        "stats": {
            "image_assigned": image_hits,
            "cells": width * height,
            "missing_art_states": sorted(missing_states),
            "state_counts": _count_states(tiles),
        },
        "run_id": run_id,
    }

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO world_maps
              (id, preset_id, seed, width, height, age, environment, tiles_json, player_x, player_y, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              preset_id=excluded.preset_id,
              seed=excluded.seed,
              width=excluded.width,
              height=excluded.height,
              age=excluded.age,
              environment=excluded.environment,
              tiles_json=excluded.tiles_json,
              player_x=excluded.player_x,
              player_y=excluded.player_y,
              meta_json=excluded.meta_json
            """,
            (
                map_id,
                preset["id"],
                seed,
                width,
                height,
                payload["age"],
                payload["environment"],
                json.dumps(flat, ensure_ascii=True),
                start[0],
                start[1],
                json.dumps(
                    {
                        "landmarks": placed,
                        "stats": payload["stats"],
                        "features": features,
                        "visited": [f"{start[0]},{start[1]}"],
                    },
                    ensure_ascii=True,
                ),
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_world_map_id', ?)",
            (map_id,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', ?)",
            (json.dumps(True),),
        )
    payload["visited"] = [f"{start[0]},{start[1]}"]
    return payload


def _count_states(tiles: list[list[dict[str, Any]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in tiles:
        for cell in row:
            sid = cell["state"]
            counts[sid] = counts.get(sid, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _pick_start(
    tiles: list[list[dict[str, Any]]],
    rng: random.Random,
    prefer: tuple[str, ...] = (),
) -> tuple[int, int]:
    height = len(tiles)
    width = len(tiles[0])
    for pref in prefer:
        spots = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if tiles[y][x]["state"] == pref and tiles[y][x].get("walkable", True)
        ]
        if spots:
            return rng.choice(spots)
    walkable = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if tiles[y][x].get("walkable", True) and tiles[y][x]["state"] not in {"void", "water", "lava"}
    ]
    if walkable:
        return rng.choice(walkable)
    return (width // 2, height // 2)


def get_map(map_id: str | None = None) -> dict[str, Any] | None:
    with connect() as conn:
        if not map_id:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'active_world_map_id'"
            ).fetchone()
            map_id = str(row["value"]) if row else ""
        if not map_id:
            return None
        row = conn.execute("SELECT * FROM world_maps WHERE id = ?", (map_id,)).fetchone()
    if not row:
        return None
    item = row_to_dict(row) or {}
    tiles = json.loads(item.get("tiles_json") or "[]")
    meta = json.loads(item.get("meta_json") or "{}")
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    grid: list[list[dict[str, Any]]] = []
    if width and height and len(tiles) == width * height:
        for y in range(height):
            grid.append(tiles[y * width : (y + 1) * width])
    return {
        "id": item.get("id"),
        "preset_id": item.get("preset_id"),
        "seed": item.get("seed"),
        "width": width,
        "height": height,
        "age": item.get("age"),
        "environment": item.get("environment"),
        "player": {"x": item.get("player_x"), "y": item.get("player_y")},
        "tiles": tiles,
        "grid": grid,
        "landmarks": meta.get("landmarks") or [],
        "stats": meta.get("stats") or {},
        "visited": meta.get("visited") or [],
        "features": meta.get("features") or {},
        "run_id": item.get("id"),
        "created_at": item.get("created_at"),
    }


def list_maps(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, preset_id, seed, width, height, age, environment, player_x, player_y, created_at
            FROM world_maps
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(100, limit)),),
        ).fetchall()
    return rows_to_dicts(rows)


def ascii_preview(map_data: dict[str, Any]) -> str:
    """Compact text preview for logs / UI."""
    glyphs = {
        "water": "~",
        "plains": ".",
        "forest": "T",
        "desert": ":",
        "mountain": "^",
        "hill": "n",
        "cliff": "|",
        "city": "#",
        "town": "o",
        "village": "v",
        "road": "-",
        "ruins": "x",
        "monolith": "!",
        "waterfall": "f",
        "void": " ",
        "asteroid": "*",
        "station": "H",
        "gate": "@",
        "nebula": "%",
        "wreck": "w",
        "ash": ",",
        "lava": "=",
        "ice": "+",
        "harbor": "u",
        "dungeon": "D",
        "cavern": "c",
        "mushroom": "m",
        "crystal": "y",
        "volcano": "A",
        "colony": "C",
        "shipyard": "S",
        "anomaly": "?",
        "beach": "b",
        "swamp": "s",
        "tundra": "_",
        "farm": "a",
        "bridge": "=",
        "mesa": "M",
    }
    grid = map_data.get("grid") or []
    # Rebuild grid from flat tiles when API responses drop nested grid.
    if not grid:
        tiles = map_data.get("tiles") or []
        width = int(map_data.get("width") or 0)
        height = int(map_data.get("height") or 0)
        if width and height and len(tiles) == width * height:
            grid = [tiles[y * width : (y + 1) * width] for y in range(height)]
        elif tiles and isinstance(tiles[0], dict) and "x" in tiles[0]:
            max_x = max(int(t.get("x") or 0) for t in tiles) + 1
            max_y = max(int(t.get("y") or 0) for t in tiles) + 1
            grid = [[{"state": "?", "x": x, "y": y} for x in range(max_x)] for y in range(max_y)]
            for t in tiles:
                try:
                    grid[int(t.get("y") or 0)][int(t.get("x") or 0)] = t
                except (IndexError, TypeError, ValueError):
                    pass
    if not grid:
        return "(empty map — press Generate)"
    px = (map_data.get("player") or {}).get("x")
    py = (map_data.get("player") or {}).get("y")
    try:
        px = int(px) if px is not None else None
        py = int(py) if py is not None else None
    except (TypeError, ValueError):
        px, py = None, None
    lines = []
    for y, row in enumerate(grid):
        chars = []
        for x, cell in enumerate(row):
            if not isinstance(cell, dict):
                chars.append("?")
                continue
            if px is not None and py is not None and x == px and y == py:
                chars.append("@")
            else:
                chars.append(glyphs.get(str(cell.get("state") or ""), "?"))
        lines.append("".join(chars))
    return "\n".join(lines)


SETTLEMENT_STATES = {
    "city",
    "town",
    "village",
    "station",
    "colony",
    "harbor",
    "ruins",
    "dungeon",
    "shipyard",
    "gate",
}


def _rebuild_grid(map_data: dict[str, Any]) -> list[list[dict[str, Any]]]:
    grid = map_data.get("grid") or []
    if grid:
        return grid
    tiles = map_data.get("tiles") or []
    width = int(map_data.get("width") or 0)
    height = int(map_data.get("height") or 0)
    if width and height and len(tiles) == width * height:
        return [tiles[y * width : (y + 1) * width] for y in range(height)]
    if tiles and isinstance(tiles[0], dict) and "x" in tiles[0]:
        max_x = max(int(t.get("x") or 0) for t in tiles) + 1
        max_y = max(int(t.get("y") or 0) for t in tiles) + 1
        grid = [[{"state": "?", "x": x, "y": y, "walkable": True} for x in range(max_x)] for y in range(max_y)]
        for t in tiles:
            try:
                grid[int(t.get("y") or 0)][int(t.get("x") or 0)] = t
            except (IndexError, TypeError, ValueError):
                pass
        return grid
    return []


def _save_map_payload(map_data: dict[str, Any]) -> None:
    """Persist player position, visited, tiles back to world_maps."""
    map_id = str(map_data.get("id") or "")
    if not map_id:
        return
    width = int(map_data.get("width") or 0)
    height = int(map_data.get("height") or 0)
    tiles = map_data.get("tiles") or []
    if not tiles:
        grid = _rebuild_grid(map_data)
        tiles = [cell for row in grid for cell in row]
    player = map_data.get("player") or {}
    meta = {
        "landmarks": map_data.get("landmarks") or [],
        "stats": map_data.get("stats") or {},
        "visited": map_data.get("visited") or [],
        "features": (map_data.get("features") or {}),
    }
    with connect() as conn:
        conn.execute(
            """
            UPDATE world_maps
            SET tiles_json = ?, player_x = ?, player_y = ?, meta_json = ?
            WHERE id = ?
            """,
            (
                json.dumps(tiles, ensure_ascii=True),
                int(player.get("x") or 0),
                int(player.get("y") or 0),
                json.dumps(meta, ensure_ascii=True),
                map_id,
            ),
        )


def mark_visited(map_data: dict[str, Any], x: int, y: int, radius: int = 1) -> list[str]:
    visited = set(str(v) for v in (map_data.get("visited") or []))
    width = int(map_data.get("width") or 0)
    height = int(map_data.get("height") or 0)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                visited.add(f"{nx},{ny}")
    map_data["visited"] = sorted(visited)
    return map_data["visited"]


def list_settlements(map_data: dict[str, Any]) -> list[dict[str, Any]]:
    grid = _rebuild_grid(map_data)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    # landmarks first
    for lm in map_data.get("landmarks") or []:
        if not isinstance(lm, dict):
            continue
        key = f"{lm.get('x')},{lm.get('y')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "x": lm.get("x"),
                "y": lm.get("y"),
                "state": lm.get("state") or lm.get("kind") or "landmark",
                "name": lm.get("name") or lm.get("label") or lm.get("state") or "Landmark",
                "summary": lm.get("summary") or lm.get("description") or "",
                "kind": "landmark",
            }
        )
    for row in grid:
        for cell in row:
            if not isinstance(cell, dict):
                continue
            state = str(cell.get("state") or "")
            if state not in SETTLEMENT_STATES:
                continue
            key = f"{cell.get('x')},{cell.get('y')}"
            if key in seen:
                continue
            seen.add(key)
            label = state.replace("_", " ").title()
            out.append(
                {
                    "x": cell.get("x"),
                    "y": cell.get("y"),
                    "state": state,
                    "name": label,
                    "summary": f"{label} on the map.",
                    "kind": "settlement",
                    "walkable": bool(cell.get("walkable", True)),
                    "elevation": cell.get("elevation"),
                }
            )
    return out


def local_map_view(map_data: dict[str, Any], *, radius: int = 4) -> dict[str, Any]:
    """Relative viewport around the player for the mini-map."""
    grid = _rebuild_grid(map_data)
    if not grid:
        return {"empty": True, "tiles": [], "radius": radius}
    width = len(grid[0])
    height = len(grid)
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    radius = max(2, min(12, int(radius or 4)))
    visited = set(str(v) for v in (map_data.get("visited") or []))
    # Ensure current neighborhood is visited
    mark_visited(map_data, px, py, radius=1)
    visited = set(str(v) for v in (map_data.get("visited") or []))

    local: list[dict[str, Any]] = []
    for y in range(max(0, py - radius), min(height, py + radius + 1)):
        for x in range(max(0, px - radius), min(width, px + radius + 1)):
            cell = dict(grid[y][x] if isinstance(grid[y][x], dict) else {})
            key = f"{x},{y}"
            cell["x"] = x
            cell["y"] = y
            cell["rel_x"] = x - px
            cell["rel_y"] = y - py
            cell["visited"] = key in visited
            cell["is_player"] = x == px and y == py
            cell["is_settlement"] = str(cell.get("state") or "") in SETTLEMENT_STATES
            # Ensure image fields exist for 16/32-bit sprite painting in the UI.
            if not cell.get("image_data_url") and not cell.get("image_path"):
                try:
                    img = pick_image_for_state(str(cell.get("state") or ""), run_id=str(map_data.get("run_id") or map_data.get("id") or ""))
                    if img:
                        cell["image_id"] = img.get("id")
                        cell["image_path"] = img.get("path") or ""
                        cell["image_data_url"] = img.get("data_url") or ""
                except Exception:
                    pass
            local.append(cell)
    return {
        "empty": False,
        "radius": radius,
        "player": {"x": px, "y": py},
        "width": width,
        "height": height,
        "tiles": local,
        "visited_count": len(visited),
        "tile_style": "pixel-16-32",
        "settlements_nearby": [
            s
            for s in list_settlements(map_data)
            if abs(int(s.get("x") or 0) - px) <= radius and abs(int(s.get("y") or 0) - py) <= radius
        ],
    }


def full_map_view(map_data: dict[str, Any]) -> dict[str, Any]:
    """Full map for the overlay: fog unvisited, highlight settlements."""
    grid = _rebuild_grid(map_data)
    width = int(map_data.get("width") or (len(grid[0]) if grid else 0))
    height = int(map_data.get("height") or len(grid))
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    visited = set(str(v) for v in (map_data.get("visited") or []))
    if f"{px},{py}" not in visited:
        mark_visited(map_data, px, py, radius=1)
        visited = set(str(v) for v in (map_data.get("visited") or []))
        _save_map_payload(map_data)
    tiles: list[dict[str, Any]] = []
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            c = dict(cell) if isinstance(cell, dict) else {"state": "?", "x": x, "y": y}
            key = f"{x},{y}"
            c["x"] = x
            c["y"] = y
            c["visited"] = key in visited
            c["is_player"] = x == px and y == py
            c["is_settlement"] = str(c.get("state") or "") in SETTLEMENT_STATES
            c["fog"] = key not in visited and not c["is_player"]
            tiles.append(c)
    return {
        "empty": False,
        "id": map_data.get("id"),
        "preset_id": map_data.get("preset_id"),
        "seed": map_data.get("seed"),
        "width": width,
        "height": height,
        "age": map_data.get("age"),
        "environment": map_data.get("environment"),
        "player": {"x": px, "y": py},
        "tiles": tiles,
        "settlements": list_settlements(map_data),
        "visited": sorted(visited),
        "stats": map_data.get("stats") or {},
        "ascii": ascii_preview(map_data),
    }


def move_player(map_id: str | None, x: int, y: int) -> dict[str, Any]:
    data = get_map(map_id)
    if not data:
        raise ValueError("No active map.")
    # restore visited from meta
    meta_visited = []
    try:
        # get_map already folds some meta; ensure visited list
        meta_visited = list(data.get("visited") or [])
    except Exception:
        meta_visited = []
    # reload meta from DB for visited if missing
    if not meta_visited:
        with connect() as conn:
            row = conn.execute("SELECT meta_json FROM world_maps WHERE id = ?", (data["id"],)).fetchone()
        if row:
            try:
                meta = json.loads(row["meta_json"] or "{}")
                meta_visited = list(meta.get("visited") or [])
            except Exception:
                meta_visited = []
    data["visited"] = meta_visited

    grid = _rebuild_grid(data)
    width = len(grid[0]) if grid else 0
    height = len(grid)
    x, y = int(x), int(y)
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("Destination out of bounds.")
    cell = grid[y][x]
    if not bool(cell.get("walkable", True)) or str(cell.get("state") or "") in {"void", "water", "lava", "cliff"}:
        raise ValueError("That tile is not walkable.")
    px = int((data.get("player") or {}).get("x") or 0)
    py = int((data.get("player") or {}).get("y") or 0)
    dist = abs(x - px) + abs(y - py)
    if dist > 8:
        raise ValueError("Too far for a single walk — pick a closer tile.")
    data["player"] = {"x": x, "y": y}
    mark_visited(data, x, y, radius=1)
    flat = [c for row in grid for c in row]
    data["tiles"] = flat
    data["grid"] = grid
    _save_map_payload(data)
    return full_map_view(data)


def suggest_tile_prompt(state_id: str, *, quality: str = "8bit", preset_id: str = "") -> str:
    meta = get_tile_state(state_id) or {"label": state_id, "description": "", "tags": []}
    preset = get_world_preset(preset_id) if preset_id else None
    style = "pixel art tile, 8-bit, top-down RPG, seamless edge-friendly" if quality == "8bit" else "detailed top-down RPG terrain tile"
    bits = [style, f"{meta.get('label') or state_id} terrain"]
    if meta.get("description"):
        bits.append(str(meta["description"]))
    tags = meta.get("tags") or []
    if tags:
        bits.append(", ".join(tags))
    if preset:
        bits.append(f"world age {preset.get('age')}, environment {preset.get('environment')}")
    return ", ".join(bits)
