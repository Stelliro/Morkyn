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
                    },
                    ensure_ascii=True,
                ),
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_world_map_id', ?)",
            (map_id,),
        )
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
    if not grid:
        return ""
    px = (map_data.get("player") or {}).get("x")
    py = (map_data.get("player") or {}).get("y")
    lines = []
    for y, row in enumerate(grid):
        chars = []
        for x, cell in enumerate(row):
            if x == px and y == py:
                chars.append("@")
            else:
                chars.append(glyphs.get(cell.get("state"), "?"))
        lines.append("".join(chars))
    return "\n".join(lines)


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
