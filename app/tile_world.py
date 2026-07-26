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
    # Larger default worlds so travel and fog matter (was 32×32 postage stamp).
    width = int(width or preset.get("width") or 48)
    height = int(height or preset.get("height") or 48)
    width = max(12, min(96, width))
    height = max(12, min(96, height))
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

    # Landmark + settlement stamps. Settlements are multi-tile blobs (cities ~8×8).
    settlement_pool = [
        s for s, w in weights.items()
        if w > 0 and (state_meta.get(s) or {}).get("category") == "settlement"
    ]
    landmark_only = [
        s for s, w in weights.items()
        if w > 0 and (state_meta.get(s) or {}).get("category") == "landmark"
    ]
    if not settlement_pool:
        settlement_pool = ["city", "town", "village", "farm", "harbor"]
    if not landmark_only:
        landmark_only = ["monolith", "ruins", "waterfall"]
    landmark_count = int(features.get("landmark_count") or 3)
    settlement_count = int(features.get("settlement_count") or max(2, landmark_count))
    placed: list[dict[str, Any]] = []
    settlements_meta: list[dict[str, Any]] = []

    def _settlement_blob_size(state: str) -> int:
        # Approximate footprint in tiles (cities aim ~8×8 = 64).
        sizes = {
            "city": rng.randint(48, 64),
            "colony": rng.randint(36, 56),
            "station": rng.randint(16, 36),
            "town": rng.randint(9, 20),
            "harbor": rng.randint(8, 18),
            "village": rng.randint(4, 9),
            "farm": rng.randint(2, 5),
            "shipyard": rng.randint(8, 16),
        }
        return int(sizes.get(state, rng.randint(4, 12)))

    def _stamp_blob(cx: int, cy: int, state: str, size: int) -> list[tuple[int, int]]:
        meta = state_meta.get(state) or {}
        elev = 1 if int(meta.get("elevation") or 0) >= 1 else 0
        walk = bool(meta.get("walkable", True))
        cells: list[tuple[int, int]] = []
        # Grow from center preferring already-walkable land
        frontier = [(cx, cy)]
        seen = {(cx, cy)}
        while frontier and len(cells) < size:
            x, y = frontier.pop(0)
            if not (0 <= x < width and 0 <= y < height):
                continue
            cell = tiles[y][x]
            if cell["state"] in {"void", "lava"}:
                continue
            # Don't paint deep water as city core often — allow harbor edge
            if cell["state"] == "water" and state not in {"harbor", "shipyard"} and rng.random() < 0.7:
                continue
            cell["state"] = state
            cell["elevation"] = elev if elev else cell.get("elevation", 0)
            cell["walkable"] = walk
            cell["settlement_class"] = state
            cells.append((x, y))
            for nx, ny in _neighbors(x, y, width, height):
                if (nx, ny) not in seen:
                    seen.add((nx, ny))
                    frontier.append((nx, ny))
            rng.shuffle(frontier)
        return cells

    for i in range(settlement_count):
        for _attempt in range(50):
            x, y = rng.randrange(width), rng.randrange(height)
            cell = tiles[y][x]
            if cell["state"] in {"water", "void", "lava", "mountain", "cliff"} and rng.random() < 0.9:
                continue
            state = _weighted_pick(
                {k: float(weights.get(k, 1) or 1) for k in settlement_pool},
                rng,
            )
            size = _settlement_blob_size(state)
            blob = _stamp_blob(x, y, state, size)
            if len(blob) < max(1, size // 4):
                continue
            xs = [p[0] for p in blob]
            ys = [p[1] for p in blob]
            sid = f"S{i + 1}"
            for bx, by in blob:
                tiles[by][bx]["settlement_id"] = sid
            # Hierarchy seed: ruler power rank by settlement class
            ruler_rank = {
                "city": rng.randint(70, 95),
                "colony": rng.randint(65, 90),
                "station": rng.randint(55, 85),
                "town": rng.randint(45, 70),
                "harbor": rng.randint(40, 65),
                "village": rng.randint(25, 45),
                "farm": rng.randint(10, 30),
                "shipyard": rng.randint(35, 60),
            }.get(state, 40)
            pop_band = {
                "city": "large",
                "colony": "large",
                "station": "medium",
                "town": "medium",
                "harbor": "medium",
                "village": "small",
                "farm": "tiny",
            }.get(state, "small")
            cx = sum(xs) // len(xs)
            cy = sum(ys) // len(ys)
            settlements_meta.append(
                {
                    "id": sid,
                    "x": cx,
                    "y": cy,
                    "state": state,
                    "class": state,
                    "tile_count": len(blob),
                    "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "population_band": pop_band,
                    "ruler_power_rank": ruler_rank,
                    "crowd_index": min(1.0, 0.25 + len(blob) / 80.0),
                    "danger_index": 0.15 if state in {"city", "town", "village", "harbor"} else 0.35,
                }
            )
            placed.append({"x": cx, "y": cy, "state": state, "settlement_id": sid, "tile_count": len(blob)})
            break

    for _ in range(max(1, landmark_count // 2)):
        for _attempt in range(40):
            x, y = rng.randrange(width), rng.randrange(height)
            cell = tiles[y][x]
            if cell["state"] in {"water", "void", "lava"} and rng.random() < 0.85:
                continue
            if cell.get("settlement_id"):
                continue
            state = _weighted_pick(
                {k: float(weights.get(k, 1) or 1) for k in landmark_only},
                rng,
            )
            meta = state_meta.get(state) or {}
            cell["state"] = state
            cell["elevation"] = 1 if int(meta.get("elevation") or 0) >= 1 else cell["elevation"]
            cell["walkable"] = bool(meta.get("walkable", True))
            placed.append({"x": x, "y": y, "state": state})
            break

    # Roads between larger settlements (safer corridors; higher bandit share on paths)
    road_cells = 0
    hubs = [
        (int(s["x"]), int(s["y"]))
        for s in settlements_meta
        if str(s.get("state") or "") in {"city", "town", "harbor", "colony", "station", "village"}
    ]
    if len(hubs) >= 2:
        for i in range(len(hubs) - 1):
            road_cells += _carve_road_between(tiles, hubs[i], hubs[i + 1], rng)
        # A few cross-links
        if len(hubs) >= 3 and rng.random() < 0.7:
            road_cells += _carve_road_between(tiles, hubs[0], hubs[-1], rng)

    hidden_bases = _place_hidden_bases(tiles, settlements_meta, rng)

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
        "settlements_meta": settlements_meta,
        "hidden_bases": hidden_bases,
        "tiles": flat,
        "grid": tiles,
        "stats": {
            "image_assigned": image_hits,
            "cells": width * height,
            "missing_art_states": sorted(missing_states),
            "state_counts": _count_states(tiles),
            "settlement_count": len(settlements_meta),
            "road_cells": road_cells,
            "hidden_bases": len(hidden_bases),
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
                        "settlements_meta": settlements_meta,
                        "hidden_bases": hidden_bases,
                        "stats": payload["stats"],
                        "features": features,
                        "visited": [f"{start[0]},{start[1]}"],
                        "knowledge": {"settlements": [], "danger": [], "notes": [], "sources": []},
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
    payload["knowledge"] = {"settlements": [], "danger": [], "notes": [], "sources": []}
    # Standing vision on spawn (radius 1, LOS-aware).
    mark_visited(payload, start[0], start[1], radius=DEFAULT_VISION_RADIUS, save=True)
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
        "settlements_meta": meta.get("settlements_meta") or [],
        "hidden_bases": meta.get("hidden_bases") or [],
        "stats": meta.get("stats") or {},
        "visited": meta.get("visited") or [],
        "features": meta.get("features") or {},
        "knowledge": meta.get("knowledge") or {"settlements": [], "danger": [], "notes": []},
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
        "gate": "G",
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
    knowledge = map_data.get("knowledge")
    if not isinstance(knowledge, dict):
        knowledge = {"settlements": [], "danger": [], "notes": []}
    meta = {
        "landmarks": map_data.get("landmarks") or [],
        "settlements_meta": map_data.get("settlements_meta") or [],
        "hidden_bases": map_data.get("hidden_bases") or [],
        "stats": map_data.get("stats") or {},
        "visited": map_data.get("visited") or [],
        "features": (map_data.get("features") or {}),
        "knowledge": knowledge,
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


# Terrain that stops line-of-sight past the first ridge (you can see the face, not past it).
SIGHT_BLOCKERS = frozenset({"mountain", "cliff", "volcano"})
# Default ground vision: Chebyshev radius 1 → player tile + immediate ring (no long scouting).
DEFAULT_VISION_RADIUS = 1


def _ensure_knowledge(map_data: dict[str, Any]) -> dict[str, Any]:
    raw = map_data.get("knowledge")
    if not isinstance(raw, dict):
        raw = {}
    knowledge = {
        "settlements": list(raw.get("settlements") or []),
        "danger": [d for d in (raw.get("danger") or []) if isinstance(d, dict)],
        "notes": [n for n in (raw.get("notes") or []) if isinstance(n, dict)],
        "sources": list(raw.get("sources") or []),
    }
    map_data["knowledge"] = knowledge
    return knowledge


def _observer_height_from_cell(cell: dict[str, Any] | None, survey_bonus: int = 0) -> int:
    """Ground=0, hill/ridge=1, mountain/peak/tower survey=2+."""
    if not isinstance(cell, dict):
        return max(0, int(survey_bonus or 0))
    elev = int(cell.get("elevation") or 0)
    state = str(cell.get("state") or "")
    h = elev
    if state in {"mountain", "volcano"}:
        h = max(h, 2)
    elif state in {"hill", "cliff", "mesa"}:
        h = max(h, 1)
    return max(0, h + int(survey_bonus or 0))


def _cell_blocks_sight(
    cell: dict[str, Any] | None,
    *,
    observer_height: int = 0,
    clarity: float = 1.0,
) -> bool:
    """Whether this intermediate tile blocks seeing *past* it."""
    if not isinstance(cell, dict):
        return False
    state = str(cell.get("state") or "")
    if state not in SIGHT_BLOCKERS:
        return False
    clarity = max(0.0, min(1.5, float(clarity or 1.0)))
    oh = int(observer_height or 0)
    # High vantage + clear air can look past ordinary ridges (DM survey decision).
    if oh >= 2 and clarity >= 0.75 and state != "volcano":
        return False
    if oh >= 1 and clarity >= 0.9 and state == "cliff":
        return False
    return True


def _bresenham_line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Inclusive integer line from (x0,y0) to (x1,y1)."""
    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
        if len(points) > 512:
            break
    return points


def has_line_of_sight(
    grid: list[list[dict[str, Any]]],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    observer_height: int = 0,
    clarity: float = 1.0,
) -> bool:
    """True if the target tile is visible from the observer.

    Adjacent tiles (Chebyshev ≤ 1) are always visible — you see the mountain face,
    but intermediates block sight past ridges unless height/clarity allow it.
    """
    if not grid:
        return False
    height = len(grid)
    width = len(grid[0]) if height else 0
    if not (0 <= x0 < width and 0 <= y0 < height and 0 <= x1 < width and 0 <= y1 < height):
        return False
    cheb = max(abs(x1 - x0), abs(y1 - y0))
    if cheb <= 1:
        return True
    line = _bresenham_line(x0, y0, x1, y1)
    # Intermediate cells only (not observer, not destination).
    for x, y in line[1:-1]:
        cell = grid[y][x] if isinstance(grid[y][x], dict) else {}
        if _cell_blocks_sight(cell, observer_height=observer_height, clarity=clarity):
            return False
    return True


def mark_visited(
    map_data: dict[str, Any],
    x: int,
    y: int,
    radius: int = DEFAULT_VISION_RADIUS,
    *,
    height: int | None = None,
    clarity: float = 1.0,
    save: bool = False,
) -> list[str]:
    """Reveal tiles the player can *see* from (x,y).

    Default radius is 1 (standing vision). Larger radius is for survey / high ground.
    Mountains and cliffs block line-of-sight past them unless height+clarity allow it.
    """
    visited = set(str(v) for v in (map_data.get("visited") or []))
    grid = _rebuild_grid(map_data)
    if not grid:
        width = int(map_data.get("width") or 0)
        height_map = int(map_data.get("height") or 0)
        for dy in range(-max(0, radius), max(0, radius) + 1):
            for dx in range(-max(0, radius), max(0, radius) + 1):
                if max(abs(dx), abs(dy)) > radius:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height_map:
                    visited.add(f"{nx},{ny}")
        map_data["visited"] = sorted(visited)
        if save:
            _save_map_payload(map_data)
        return map_data["visited"]

    width = len(grid[0])
    height_map = len(grid)
    radius = max(0, min(24, int(radius)))
    observer_cell = grid[y][x] if 0 <= y < height_map and 0 <= x < width else {}
    observer_height = (
        int(height)
        if height is not None
        else _observer_height_from_cell(observer_cell, survey_bonus=0)
    )
    clarity = max(0.0, min(1.5, float(clarity if clarity is not None else 1.0)))

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            # Circular vision footprint (not a square diamond of corners only — use euclidean).
            if (dx * dx + dy * dy) > (radius * radius) + 0.25 and max(abs(dx), abs(dy)) > radius:
                continue
            # Prefer circular: radius 1 = center + 4-orth + diagonals still within r√2≈1.41 → include cheb≤1
            if radius <= 1:
                if max(abs(dx), abs(dy)) > 1:
                    continue
            else:
                if (dx * dx + dy * dy) > (radius + 0.35) ** 2:
                    continue
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height_map):
                continue
            if has_line_of_sight(
                grid, x, y, nx, ny, observer_height=observer_height, clarity=clarity
            ):
                visited.add(f"{nx},{ny}")
    map_data["visited"] = sorted(visited)
    if save:
        _save_map_payload(map_data)
    return map_data["visited"]


def apply_survey(
    map_data: dict[str, Any],
    *,
    radius: int = 3,
    height: int | None = None,
    clarity: float = 1.0,
) -> dict[str, Any]:
    """DM/player survey: expand vision with height and clarity (fog clarity at distance)."""
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    clarity = max(0.15, min(1.5, float(clarity if clarity is not None else 1.0)))
    # Poor clarity shortens how far the survey actually reaches.
    effective_radius = max(1, int(round(int(radius) * clarity)))
    before = len(map_data.get("visited") or [])
    grid = _rebuild_grid(map_data)
    observer_cell = None
    if grid and 0 <= py < len(grid) and 0 <= px < len(grid[0]):
        observer_cell = grid[py][px]
    # Explicit survey height is a bonus on top of standing terrain (tower, tree, cliff edge).
    base_h = _observer_height_from_cell(observer_cell, survey_bonus=0)
    oh = base_h if height is None else max(base_h, int(height))
    mark_visited(
        map_data,
        px,
        py,
        radius=effective_radius,
        height=oh,
        clarity=clarity,
        save=True,
    )
    after = len(map_data.get("visited") or [])
    return {
        "ok": True,
        "player": {"x": px, "y": py},
        "radius_requested": int(radius),
        "radius_effective": effective_radius,
        "height": oh,
        "clarity": clarity,
        "tiles_revealed": max(0, after - before),
        "visited_count": after,
    }


def grant_map_knowledge(
    map_data: dict[str, Any],
    *,
    settlement_ids: list[str] | None = None,
    danger: list[dict[str, Any]] | None = None,
    notes: list[dict[str, Any]] | None = None,
    source: str = "rumor",
    save: bool = True,
) -> dict[str, Any]:
    """Reveal towns / danger hotspots as intel without full terrain vision.

    Used when the player talks to locals, studies a map, or has lived in the area.
    """
    knowledge = _ensure_knowledge(map_data)
    known_set = {str(s) for s in knowledge["settlements"]}
    for sid in settlement_ids or []:
        sid_s = str(sid).strip()
        if sid_s:
            known_set.add(sid_s)
    knowledge["settlements"] = sorted(known_set)

    def _merge_markers(bucket: str, items: list[dict[str, Any]] | None) -> None:
        if not items:
            return
        existing = list(knowledge.get(bucket) or [])
        seen = {
            f"{m.get('x')},{m.get('y')}|{m.get('label') or m.get('id') or ''}"
            for m in existing
            if isinstance(m, dict)
        }
        for raw in items:
            if not isinstance(raw, dict):
                continue
            try:
                mx = int(raw.get("x"))
                my = int(raw.get("y"))
            except (TypeError, ValueError):
                continue
            label = str(raw.get("label") or raw.get("name") or raw.get("kind") or "mark")[:80]
            key = f"{mx},{my}|{label}"
            if key in seen:
                continue
            seen.add(key)
            existing.append(
                {
                    "id": str(raw.get("id") or f"{bucket[0]}{mx}_{my}"),
                    "x": mx,
                    "y": my,
                    "label": label,
                    "kind": str(raw.get("kind") or bucket),
                    "source": str(raw.get("source") or source)[:40],
                    "summary": str(raw.get("summary") or "")[:240],
                }
            )
        knowledge[bucket] = existing

    _merge_markers("danger", danger)
    _merge_markers("notes", notes)
    src = str(source or "rumor").strip()[:60]
    if src and src not in knowledge["sources"]:
        knowledge["sources"] = (list(knowledge["sources"]) + [src])[-40:]
    map_data["knowledge"] = knowledge
    if save:
        _save_map_payload(map_data)
    return knowledge


def grant_lived_area_knowledge(
    map_data: dict[str, Any],
    *,
    age: int = 25,
    traveler: bool = True,
    home_x: int | None = None,
    home_y: int | None = None,
    source: str = "lived",
) -> dict[str, Any]:
    """Someone who grew up or traveled here knows towns and rough danger zones.

    Age and traveler flag scale how far that memory reaches — a 40-year-old
    road-worn PC knows more than a sheltered 18-year-old.
    """
    px = int(home_x if home_x is not None else (map_data.get("player") or {}).get("x") or 0)
    py = int(home_y if home_y is not None else (map_data.get("player") or {}).get("y") or 0)
    age = max(12, min(120, int(age or 25)))
    # Base memory radius grows with age; travelers stretch further along roads.
    radius = 4 + (age // 10) + (4 if traveler else 0)
    radius = min(22, radius)

    settlement_ids: list[str] = []
    for sm in map_data.get("settlements_meta") or []:
        if not isinstance(sm, dict):
            continue
        sx = int(sm.get("x") or 0)
        sy = int(sm.get("y") or 0)
        dist = max(abs(sx - px), abs(sy - py))
        # Closer towns almost always known; far ones only for older travelers.
        if dist <= radius or (traveler and dist <= radius + 4 and age >= 30):
            settlement_ids.append(str(sm.get("id") or f"{sx},{sy}"))

    danger: list[dict[str, Any]] = []
    for hb in map_data.get("hidden_bases") or []:
        if not isinstance(hb, dict):
            continue
        hx = int(hb.get("x") or 0)
        hy = int(hb.get("y") or 0)
        dist = max(abs(hx - px), abs(hy - py))
        if dist > radius + 2:
            continue
        # Lived knowledge is approximate rumors, not exact scout reports.
        if not hb.get("discovered") and dist > 3 and age < 35 and not traveler:
            continue
        owner = str(hb.get("owner") or "camp")
        danger.append(
            {
                "id": f"lived-{hb.get('id') or f'{hx}_{hy}'}",
                "x": hx,
                "y": hy,
                "label": "Bandit stretch" if owner == "bandit" else "Rough country",
                "kind": "danger",
                "source": source,
                "summary": "Locals avoid this ground after dark." if owner == "bandit" else "Travelers speak carefully of this place.",
            }
        )

    # Landmark notes for famous sites in memory range
    notes: list[dict[str, Any]] = []
    for lm in map_data.get("landmarks") or []:
        if not isinstance(lm, dict):
            continue
        lx = int(lm.get("x") or 0)
        ly = int(lm.get("y") or 0)
        if max(abs(lx - px), abs(ly - py)) > radius:
            continue
        notes.append(
            {
                "id": str(lm.get("id") or lm.get("poi_id") or f"lm{lx}_{ly}"),
                "x": lx,
                "y": ly,
                "label": str(lm.get("name") or lm.get("label") or lm.get("state") or "Landmark"),
                "kind": "landmark",
                "source": source,
                "summary": str(lm.get("summary") or lm.get("description") or "")[:240],
            }
        )

    knowledge = grant_map_knowledge(
        map_data,
        settlement_ids=settlement_ids,
        danger=danger,
        notes=notes,
        source=source,
        save=True,
    )
    return {
        "ok": True,
        "radius": radius,
        "age": age,
        "traveler": bool(traveler),
        "settlements_known": len(settlement_ids),
        "danger_known": len(danger),
        "notes_known": len(notes),
        "knowledge": knowledge,
    }


def knowledge_markers_for_view(map_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten intel markers for the UI (settlements + danger + notes)."""
    knowledge = _ensure_knowledge(map_data)
    known_ids = {str(s) for s in knowledge.get("settlements") or []}
    markers: list[dict[str, Any]] = []
    for s in list_settlements(map_data):
        sid = str(s.get("id") or "")
        if sid and sid in known_ids:
            markers.append(
                {
                    "id": sid,
                    "x": s.get("x"),
                    "y": s.get("y"),
                    "label": s.get("name") or s.get("state") or "Settlement",
                    "kind": "settlement",
                    "source": "intel",
                    "summary": s.get("summary") or "",
                }
            )
    for d in knowledge.get("danger") or []:
        if isinstance(d, dict):
            markers.append({**d, "kind": d.get("kind") or "danger"})
    for n in knowledge.get("notes") or []:
        if isinstance(n, dict):
            markers.append({**n, "kind": n.get("kind") or "note"})
    return markers


def filter_settlements_for_player(map_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Settlements the player knows about (visited tile or intel) — not the full gazetteer."""
    visited = set(str(v) for v in (map_data.get("visited") or []))
    knowledge = _ensure_knowledge(map_data)
    known_ids = {str(s) for s in knowledge.get("settlements") or []}
    out: list[dict[str, Any]] = []
    for s in list_settlements(map_data):
        sid = str(s.get("id") or "")
        key = f"{s.get('x')},{s.get('y')}"
        # Settlement blob may span tiles — treat centroid or any visited cell as known.
        known_visit = key in visited
        if not known_visit and isinstance(s.get("bbox"), (list, tuple)) and len(s["bbox"]) >= 4:
            try:
                x0, y0, x1, y1 = (int(s["bbox"][i]) for i in range(4))
                for yy in range(y0, y1 + 1):
                    for xx in range(x0, x1 + 1):
                        if f"{xx},{yy}" in visited:
                            known_visit = True
                            break
                    if known_visit:
                        break
            except (TypeError, ValueError):
                pass
        if known_visit or (sid and sid in known_ids):
            item = dict(s)
            item["known_how"] = "visited" if known_visit else "intel"
            out.append(item)
    return out


def list_settlements(map_data: dict[str, Any]) -> list[dict[str, Any]]:
    grid = _rebuild_grid(map_data)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Prefer multi-tile settlement meta (one entry per city/town blob)
    for sm in map_data.get("settlements_meta") or []:
        if not isinstance(sm, dict):
            continue
        sid = str(sm.get("id") or f"{sm.get('x')},{sm.get('y')}")
        if sid in seen:
            continue
        seen.add(sid)
        state = str(sm.get("state") or sm.get("class") or "town")
        label = state.replace("_", " ").title()
        out.append(
            {
                "id": sid,
                "x": sm.get("x"),
                "y": sm.get("y"),
                "state": state,
                "name": sm.get("name") or label,
                "summary": sm.get("summary")
                or f"{label} spanning ~{sm.get('tile_count') or '?'} tiles ({sm.get('population_band') or 'settlement'}).",
                "kind": "settlement",
                "tile_count": sm.get("tile_count"),
                "population_band": sm.get("population_band"),
                "ruler_power_rank": sm.get("ruler_power_rank"),
                "crowd_index": sm.get("crowd_index"),
                "danger_index": sm.get("danger_index"),
                "bbox": sm.get("bbox"),
            }
        )
    # landmarks + discovered hidden bases
    for lm in map_data.get("landmarks") or []:
        if not isinstance(lm, dict):
            continue
        if lm.get("settlement_id"):
            continue  # already covered as settlement blob
        key = f"lm:{lm.get('id') or lm.get('poi_id') or lm.get('x')},{lm.get('y')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": lm.get("id") or lm.get("poi_id"),
                "x": lm.get("x"),
                "y": lm.get("y"),
                "state": lm.get("state") or lm.get("kind") or "landmark",
                "name": lm.get("name") or lm.get("label") or lm.get("state") or "Landmark",
                "summary": lm.get("summary") or lm.get("description") or "",
                "kind": lm.get("kind") or "landmark",
                "discovered": bool(lm.get("discovered")),
            }
        )
    for hb in map_data.get("hidden_bases") or []:
        if not isinstance(hb, dict) or not hb.get("discovered"):
            continue
        key = f"hb:{hb.get('id')}"
        if key in seen:
            continue
        seen.add(key)
        owner = str(hb.get("owner") or "camp")
        out.append(
            {
                "id": key,
                "x": hb.get("x"),
                "y": hb.get("y"),
                "state": "hidden_base",
                "name": "Bandit camp" if owner == "bandit" else "Hidden camp",
                "summary": f"Discovered {owner} hideout.",
                "kind": "hidden_base",
                "discovered": True,
            }
        )
    # Fallback: single cells without meta (old maps)
    if not any(s.get("kind") == "settlement" for s in out):
        for row in grid:
            for cell in row:
                if not isinstance(cell, dict):
                    continue
                state = str(cell.get("state") or "")
                if state not in SETTLEMENT_STATES:
                    continue
                sid = str(cell.get("settlement_id") or f"{cell.get('x')},{cell.get('y')}")
                if sid in seen:
                    continue
                seen.add(sid)
                label = state.replace("_", " ").title()
                out.append(
                    {
                        "id": sid,
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


def local_map_view(map_data: dict[str, Any], *, radius: int = 6) -> dict[str, Any]:
    """Circular viewport around the player (follows player).

    Display radius is the canvas footprint; actual *vision* is visited tiles only
    (default mark_visited radius 1 + LOS). Unvisited cells are pure fog; intel
    markers (towns / danger from locals or lived life) can still show through.
    """
    grid = _rebuild_grid(map_data)
    if not grid:
        return {"empty": True, "tiles": [], "radius": radius}
    width = len(grid[0])
    height = len(grid)
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    # Viewport size for the circular UI (not vision range).
    radius = max(3, min(14, int(radius or 6)))
    # Standing vision: 1 tile around the player with mountain LOS.
    before_visit = set(str(v) for v in (map_data.get("visited") or []))
    mark_visited(map_data, px, py, radius=DEFAULT_VISION_RADIUS, save=False)
    visited = set(str(v) for v in (map_data.get("visited") or []))
    if visited != before_visit:
        _save_map_payload(map_data)
    markers = knowledge_markers_for_view(map_data)
    markers_by_pos = {
        f"{int(m.get('x') or 0)},{int(m.get('y') or 0)}": m
        for m in markers
        if m.get("x") is not None and m.get("y") is not None
    }

    local: list[dict[str, Any]] = []
    r2 = (radius + 0.35) ** 2
    for y in range(max(0, py - radius), min(height, py + radius + 1)):
        for x in range(max(0, px - radius), min(width, px + radius + 1)):
            dx, dy = x - px, y - py
            if (dx * dx + dy * dy) > r2:
                continue
            key = f"{x},{y}"
            is_player = x == px and y == py
            is_visited = key in visited or is_player
            base = grid[y][x] if isinstance(grid[y][x], dict) else {}
            cell: dict[str, Any] = {
                "x": x,
                "y": y,
                "rel_x": dx,
                "rel_y": dy,
                "visited": is_visited,
                "is_player": is_player,
                "fog": not is_visited,
                "in_circle": True,
            }
            marker = markers_by_pos.get(key)
            if marker:
                cell["marker"] = {
                    "kind": marker.get("kind") or "note",
                    "label": marker.get("label") or "",
                    "source": marker.get("source") or "",
                }
            if is_visited:
                cell.update(
                    {
                        "state": base.get("state"),
                        "walkable": base.get("walkable", True),
                        "elevation": base.get("elevation"),
                        "settlement_id": base.get("settlement_id"),
                        "is_settlement": str(base.get("state") or "") in SETTLEMENT_STATES,
                        "image_id": base.get("image_id"),
                        "image_path": base.get("image_path") or "",
                        "image_data_url": base.get("image_data_url") or "",
                    }
                )
                if not cell.get("image_data_url") and not cell.get("image_path"):
                    try:
                        img = pick_image_for_state(
                            str(cell.get("state") or ""),
                            run_id=str(map_data.get("run_id") or map_data.get("id") or ""),
                        )
                        if img:
                            cell["image_id"] = img.get("id")
                            cell["image_path"] = img.get("path") or ""
                            cell["image_data_url"] = img.get("data_url") or ""
                    except Exception:
                        pass
            else:
                # Fog: no terrain leak. Markers may still identify a known town/danger.
                cell["state"] = "unknown"
                cell["walkable"] = None
                cell["is_settlement"] = bool(
                    marker and str(marker.get("kind") or "") in {"settlement", "town", "city"}
                )
            local.append(cell)
    known_settlements = [
        s
        for s in filter_settlements_for_player(map_data)
        if abs(int(s.get("x") or 0) - px) <= radius + 2
        and abs(int(s.get("y") or 0) - py) <= radius + 2
    ]
    return {
        "empty": False,
        "radius": radius,
        "vision_radius": DEFAULT_VISION_RADIUS,
        "shape": "circle",
        "follow_player": True,
        "player": {"x": px, "y": py},
        "width": width,
        "height": height,
        "tiles": local,
        "visited_count": len(visited),
        "tile_style": "pixel-16-32",
        "markers": markers,
        "settlements_nearby": known_settlements,
        "knowledge": _ensure_knowledge(map_data),
    }


def full_map_view(map_data: dict[str, Any]) -> dict[str, Any]:
    """Full map for the detailed overlay: pan around; fog hides unvisited terrain.

    Known settlements / danger from intel appear as markers on the fog.
    """
    grid = _rebuild_grid(map_data)
    width = int(map_data.get("width") or (len(grid[0]) if grid else 0))
    height = int(map_data.get("height") or len(grid))
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    visited = set(str(v) for v in (map_data.get("visited") or []))
    if f"{px},{py}" not in visited:
        mark_visited(map_data, px, py, radius=DEFAULT_VISION_RADIUS, save=True)
        visited = set(str(v) for v in (map_data.get("visited") or []))
    markers = knowledge_markers_for_view(map_data)
    markers_by_pos = {
        f"{int(m.get('x') or 0)},{int(m.get('y') or 0)}": m
        for m in markers
        if m.get("x") is not None and m.get("y") is not None
    }
    tiles: list[dict[str, Any]] = []
    run_id = str(map_data.get("run_id") or map_data.get("id") or "")
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            key = f"{x},{y}"
            is_player = x == px and y == py
            is_visited = key in visited or is_player
            base = cell if isinstance(cell, dict) else {"state": "?", "x": x, "y": y}
            c: dict[str, Any] = {
                "x": x,
                "y": y,
                "visited": is_visited,
                "is_player": is_player,
                "fog": not is_visited,
            }
            marker = markers_by_pos.get(key)
            if marker:
                c["marker"] = {
                    "kind": marker.get("kind") or "note",
                    "label": marker.get("label") or "",
                    "source": marker.get("source") or "",
                }
            if is_visited:
                c["state"] = base.get("state")
                c["walkable"] = base.get("walkable", True)
                c["elevation"] = base.get("elevation")
                c["settlement_id"] = base.get("settlement_id")
                c["is_settlement"] = str(base.get("state") or "") in SETTLEMENT_STATES
                c["image_id"] = base.get("image_id")
                c["image_path"] = base.get("image_path") or ""
                c["image_data_url"] = base.get("image_data_url") or ""
                if not c.get("image_data_url") and not c.get("image_path"):
                    try:
                        img = pick_image_for_state(str(c.get("state") or ""), run_id=run_id)
                        if img:
                            c["image_id"] = img.get("id")
                            c["image_path"] = img.get("path") or ""
                            c["image_data_url"] = img.get("data_url") or ""
                    except Exception:
                        pass
            else:
                # True fog-of-war: no terrain colors or sprites for unseen land.
                c["state"] = "unknown"
                c["walkable"] = None
                c["is_settlement"] = bool(
                    marker and str(marker.get("kind") or "") in {"settlement", "town", "city"}
                )
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
        "settlements": filter_settlements_for_player(map_data),
        "markers": markers,
        "knowledge": _ensure_knowledge(map_data),
        "visited": sorted(visited),
        "visited_count": len(visited),
        "vision_radius": DEFAULT_VISION_RADIUS,
        "stats": map_data.get("stats") or {},
        "ascii": ascii_preview(map_data),
        "pan": True,
        "shape": "full",
    }


# Minutes spent per adjacent step by destination terrain (paths are faster).
TERRAIN_WALK_MINUTES: dict[str, int] = {
    "road": 8,
    "bridge": 8,
    "plains": 12,
    "beach": 12,
    "farm": 12,
    "town": 10,
    "village": 10,
    "city": 10,
    "harbor": 11,
    "colony": 11,
    "station": 10,
    "forest": 18,
    "swamp": 22,
    "desert": 20,
    "tundra": 20,
    "ash": 20,
    "hill": 16,
    "mountain": 28,
    "ruins": 16,
    "dungeon": 20,
    "cavern": 18,
    "mushroom": 16,
    "ice": 18,
    "mesa": 16,
    "asteroid": 14,
    "wreck": 18,
}
# Ambush pressure by terrain: paths = safer overall but higher *bandit* share;
# forest = more wild/unknown, lower organized bandit odds.
TERRAIN_AMBUSH: dict[str, dict[str, float]] = {
    "road": {"p": 0.14, "bandit": 0.72, "wild": 0.12, "hidden_base": 0.10, "traveler": 0.06},
    "bridge": {"p": 0.12, "bandit": 0.65, "wild": 0.15, "hidden_base": 0.12, "traveler": 0.08},
    "plains": {"p": 0.10, "bandit": 0.40, "wild": 0.35, "hidden_base": 0.15, "traveler": 0.10},
    "forest": {"p": 0.16, "bandit": 0.22, "wild": 0.48, "hidden_base": 0.22, "traveler": 0.08},
    "swamp": {"p": 0.15, "bandit": 0.18, "wild": 0.55, "hidden_base": 0.20, "traveler": 0.07},
    "desert": {"p": 0.13, "bandit": 0.35, "wild": 0.40, "hidden_base": 0.18, "traveler": 0.07},
    "mountain": {"p": 0.12, "bandit": 0.25, "wild": 0.40, "hidden_base": 0.28, "traveler": 0.07},
    "hill": {"p": 0.11, "bandit": 0.30, "wild": 0.38, "hidden_base": 0.22, "traveler": 0.10},
    "ruins": {"p": 0.18, "bandit": 0.28, "wild": 0.30, "hidden_base": 0.35, "traveler": 0.07},
    "dungeon": {"p": 0.22, "bandit": 0.15, "wild": 0.45, "hidden_base": 0.35, "traveler": 0.05},
    "city": {"p": 0.06, "bandit": 0.45, "wild": 0.05, "hidden_base": 0.20, "traveler": 0.30},
    "town": {"p": 0.05, "bandit": 0.35, "wild": 0.05, "hidden_base": 0.15, "traveler": 0.45},
    "village": {"p": 0.04, "bandit": 0.25, "wild": 0.10, "hidden_base": 0.15, "traveler": 0.50},
    "farm": {"p": 0.05, "bandit": 0.30, "wild": 0.20, "hidden_base": 0.15, "traveler": 0.35},
    "harbor": {"p": 0.07, "bandit": 0.40, "wild": 0.10, "hidden_base": 0.20, "traveler": 0.30},
}


def walk_minutes_for_step(
    from_cell: dict[str, Any] | None,
    to_cell: dict[str, Any] | None,
    *,
    chebyshev_steps: int = 1,
) -> int:
    """In-world minutes for a map step; roads are quickest."""
    to_state = str((to_cell or {}).get("state") or "plains").lower()
    from_state = str((from_cell or {}).get("state") or "").lower()
    base = TERRAIN_WALK_MINUTES.get(to_state, 14)
    # Leaving a road into rough terrain is a bit slower (transition).
    if from_state == "road" and to_state not in {"road", "bridge", "town", "city", "village"}:
        base += 2
    # Diagonal feels slightly longer
    if chebyshev_steps >= 1 and abs(chebyshev_steps) == 1:
        # single step: if we only know cheb, diagonal handled by caller
        pass
    return max(5, int(base))


def roll_travel_encounter(
    to_cell: dict[str, Any] | None,
    *,
    minutes: int,
    seed: int,
    hidden_bases: list[dict[str, Any]] | None = None,
    weather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Paths: lower total chaos than deep wild, but *bandits* more likely on roads.
    Forest: higher wild/hidden-base share, lower organized bandit share.
    Weather raises overall encounter chance (server RNG).
    """
    state = str((to_cell or {}).get("state") or "plains").lower()
    table = TERRAIN_AMBUSH.get(state) or {
        "p": 0.10,
        "bandit": 0.30,
        "wild": 0.40,
        "hidden_base": 0.20,
        "traveler": 0.10,
    }
    # Longer multi-tile jumps scale exposure slightly
    hours = max(minutes, 5) / 60.0
    p = float(table["p"])
    p = 1.0 - (1.0 - p) ** max(0.15, hours * 4)  # adjacent steps still meaningful
    try:
        from app.world import weather_event_chance_delta

        p = min(0.7, p + weather_event_chance_delta(weather))
    except Exception:
        pass
    p = max(0.02, min(0.55, p))
    rng = random.Random(int(seed) & 0x7FFFFFFF)
    hit = rng.random() < p
    x = int((to_cell or {}).get("x") or 0)
    y = int((to_cell or {}).get("y") or 0)
    # Standing on a hidden base always elevates chance
    base_here = None
    for b in hidden_bases or []:
        if not isinstance(b, dict):
            continue
        if int(b.get("x") or -1) == x and int(b.get("y") or -1) == y:
            base_here = b
            hit = hit or rng.random() < 0.55
            break
    if not hit:
        return {
            "happened": False,
            "kind": "none",
            "p": round(p, 4),
            "terrain": state,
            "minutes": minutes,
        }
    weights = {
        "bandit_ambush": float(table.get("bandit") or 0.3),
        "wild_threat": float(table.get("wild") or 0.3),
        "hidden_base": float(table.get("hidden_base") or 0.2),
        "traveler": float(table.get("traveler") or 0.1),
    }
    if base_here:
        weights["hidden_base"] *= 3.0
        weights["bandit_ambush"] *= 1.5 if str(base_here.get("owner") or "") == "bandit" else 0.6
        # Undiscovered base on tile almost always becomes the encounter
        if not base_here.get("discovered") and rng.random() < 0.85:
            weights = {"hidden_base": 1.0, "bandit_ambush": 0.05, "wild_threat": 0.05, "traveler": 0.0}
    total = sum(weights.values()) or 1.0
    roll = rng.random() * total
    acc = 0.0
    kind = "wild_threat"
    for k, w in weights.items():
        acc += w
        if roll <= acc:
            kind = k
            break
    # Some encounters are "wary locals" — not evil, but bad social checks escalate
    wary = kind in {"traveler", "hidden_base"} and rng.random() < 0.55
    hostile_default = kind in {"bandit_ambush", "wild_threat"} or (
        base_here and str(base_here.get("owner") or "") == "bandit"
    )
    discovered = False
    if base_here and (kind == "hidden_base" or not base_here.get("discovered")):
        # Stepping the encounter reveals the camp as a map POI
        discovered = True
        base_here = dict(base_here)
        base_here["discovered"] = True
        base_here["discovered_at"] = f"{x},{y}"
    return {
        "happened": True,
        "kind": kind,
        "p": round(p, 4),
        "terrain": state,
        "minutes": minutes,
        "wary_not_evil": bool(wary and not hostile_default),
        "hostile_default": bool(hostile_default),
        "hidden_base": base_here,
        "base_discovered": discovered,
        "outcome_seed": rng.randint(1, 999999),
        "participant_tier": "nameless" if kind != "traveler" else "event_worthy",
    }


def mark_hidden_base_discovered(map_data: dict[str, Any], base_id: str) -> dict[str, Any] | None:
    """Persist discovery on map meta and surface as a landmark POI."""
    if not map_data or not base_id:
        return None
    bases = list(map_data.get("hidden_bases") or [])
    found = None
    for i, b in enumerate(bases):
        if not isinstance(b, dict):
            continue
        if str(b.get("id")) != str(base_id):
            continue
        b = dict(b)
        b["discovered"] = True
        bases[i] = b
        found = b
        break
    if not found:
        return None
    map_data["hidden_bases"] = bases
    landmarks = list(map_data.get("landmarks") or [])
    key = f"hb:{found.get('id')}"
    if not any(str(lm.get("id") or lm.get("poi_id") or "") == key for lm in landmarks if isinstance(lm, dict)):
        owner = str(found.get("owner") or "camp")
        landmarks.append(
            {
                "id": key,
                "poi_id": key,
                "x": found.get("x"),
                "y": found.get("y"),
                "state": "ruins" if owner == "bandit" else "farm",
                "name": "Bandit camp" if owner == "bandit" else "Hidden camp",
                "kind": "hidden_base",
                "summary": f"Discovered {owner} hideout.",
                "discovered": True,
            }
        )
    map_data["landmarks"] = landmarks
    # Mark cell for UI
    try:
        grid = _rebuild_grid(map_data)
        bx, by = int(found.get("x") or 0), int(found.get("y") or 0)
        if 0 <= by < len(grid) and 0 <= bx < len(grid[0]):
            grid[by][bx]["poi"] = "hidden_base"
            grid[by][bx]["poi_discovered"] = True
            grid[by][bx]["hidden_base_id"] = found.get("id")
            map_data["grid"] = grid
            map_data["tiles"] = [c for row in grid for c in row]
    except Exception:
        pass
    _save_map_payload(map_data)
    return found


def _carve_road_between(
    tiles: list[list[dict[str, Any]]],
    a: tuple[int, int],
    b: tuple[int, int],
    rng: random.Random,
) -> int:
    """Simple L-shaped / noisy path as road tiles (safer travel corridors)."""
    width = len(tiles[0]) if tiles else 0
    height = len(tiles)
    x0, y0 = a
    x1, y1 = b
    painted = 0
    x, y = x0, y0
    # Prefer horizontal-first or vertical-first
    horiz_first = rng.random() < 0.5
    path: list[tuple[int, int]] = [(x, y)]
    if horiz_first:
        while x != x1:
            x += 1 if x1 > x else -1
            path.append((x, y))
        while y != y1:
            y += 1 if y1 > y else -1
            path.append((x, y))
    else:
        while y != y1:
            y += 1 if y1 > y else -1
            path.append((x, y))
        while x != x1:
            x += 1 if x1 > x else -1
            path.append((x, y))
    for px, py in path:
        if not (0 <= px < width and 0 <= py < height):
            continue
        cell = tiles[py][px]
        if cell.get("state") in {"water", "void", "lava", "cliff", "mountain"}:
            continue
        if cell.get("settlement_id") and cell.get("state") in SETTLEMENT_STATES:
            continue  # don't overwrite dense city cores with road
        cell["state"] = "road"
        cell["walkable"] = True
        cell["elevation"] = int(cell.get("elevation") or 0)
        painted += 1
    return painted


def _place_hidden_bases(
    tiles: list[list[dict[str, Any]]],
    settlements_meta: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Bandit camps and civilian hideouts off the main roads."""
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    bases: list[dict[str, Any]] = []
    count = max(2, min(8, (width * height) // 180))
    prefer = {"forest", "swamp", "hill", "ruins", "mountain", "cavern", "ash", "desert"}
    for i in range(count):
        for _ in range(40):
            x, y = rng.randrange(width), rng.randrange(height)
            cell = tiles[y][x]
            st = str(cell.get("state") or "")
            if st in {"water", "void", "lava", "road", "city", "town", "village", "harbor"}:
                continue
            if st not in prefer and rng.random() < 0.55:
                continue
            # Away from settlement centroids
            too_close = False
            for sm in settlements_meta:
                if abs(int(sm.get("x") or 0) - x) + abs(int(sm.get("y") or 0) - y) < 4:
                    too_close = True
                    break
            if too_close:
                continue
            owner = "bandit" if rng.random() < 0.55 else "civilian"
            base = {
                "id": f"HB{i + 1}",
                "x": x,
                "y": y,
                "owner": owner,
                "power_rank": rng.randint(15, 45) if owner == "bandit" else rng.randint(5, 25),
                "hidden": True,
                "discovered": False,
            }
            cell["hidden_base_id"] = base["id"]
            cell["poi"] = "hidden_base"
            bases.append(base)
            break
    return bases


def restore_player_position(map_id: str | None, x: int, y: int) -> dict[str, Any]:
    """Move player marker without travel costs (used to undo blocked walks)."""
    data = get_map(map_id)
    if not data:
        raise ValueError("No active map.")
    grid = _rebuild_grid(data)
    width = len(grid[0]) if grid else 0
    height = len(grid)
    x, y = int(x), int(y)
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("Destination out of bounds.")
    data["player"] = {"x": x, "y": y}
    flat = [c for row in grid for c in row]
    data["tiles"] = flat
    data["grid"] = grid
    _save_map_payload(data)
    return full_map_view(data)


def move_player(map_id: str | None, x: int, y: int) -> dict[str, Any]:
    """Move player; attaches `travel` meta (minutes, terrain, encounter roll)."""
    data = get_map(map_id)
    if not data:
        raise ValueError("No active map.")
    meta_visited = list(data.get("visited") or [])
    if not meta_visited or not data.get("knowledge"):
        with connect() as conn:
            row = conn.execute("SELECT meta_json FROM world_maps WHERE id = ?", (data["id"],)).fetchone()
        if row:
            try:
                meta = json.loads(row["meta_json"] or "{}")
                if not meta_visited:
                    meta_visited = list(meta.get("visited") or [])
                if not data.get("settlements_meta"):
                    data["settlements_meta"] = meta.get("settlements_meta") or []
                if not data.get("hidden_bases"):
                    data["hidden_bases"] = meta.get("hidden_bases") or []
                if not data.get("knowledge"):
                    data["knowledge"] = meta.get("knowledge") or {
                        "settlements": [],
                        "danger": [],
                        "notes": [],
                        "sources": [],
                    }
            except Exception:
                if not meta_visited:
                    meta_visited = []
    data["visited"] = meta_visited
    _ensure_knowledge(data)

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
    manh = abs(x - px) + abs(y - py)
    cheb = max(abs(x - px), abs(y - py))
    if cheb > 1 and manh > 8:
        raise ValueError("Too far for a single walk — step with arrows or pick a closer tile.")
    if manh == 0:
        view = full_map_view(data)
        view["travel"] = {"minutes": 0, "steps": 0, "encounter": {"happened": False}}
        return view

    from_cell = grid[py][px] if 0 <= py < height and 0 <= px < width else {}
    # Multi-step jumps: charge minutes per Chebyshev step at destination terrain
    steps = max(1, cheb)
    per = walk_minutes_for_step(from_cell, cell, chebyshev_steps=1)
    minutes = per * steps
    # Weather slows travel (server-side; independent of LLM)
    weather_mult = 1.0
    weather_snapshot: dict[str, Any] = {}
    try:
        from app.world import get_weather, weather_travel_multiplier, weather_event_chance_delta

        with connect() as _wc:
            weather_snapshot = get_weather(_wc)
        weather_mult = weather_travel_multiplier(weather_snapshot)
        minutes = max(5, int(round(minutes * weather_mult)))
    except Exception:
        weather_mult = 1.0
    seed = (
        int(data.get("seed") or 0)
        ^ (x * 73856093)
        ^ (y * 19349663)
        ^ (px * 83492791)
        ^ (py * 12347)
        ^ (len(data.get("visited") or []) * 17)
    )
    encounter = roll_travel_encounter(
        {**cell, "x": x, "y": y},
        minutes=minutes,
        seed=seed,
        hidden_bases=list(data.get("hidden_bases") or []),
        weather=weather_snapshot,
    )
    settlement_id = cell.get("settlement_id")
    settlement_meta = None
    if settlement_id:
        for sm in data.get("settlements_meta") or []:
            if str(sm.get("id")) == str(settlement_id):
                settlement_meta = sm
                break

    data["player"] = {"x": x, "y": y}
    mark_visited(data, x, y, radius=DEFAULT_VISION_RADIUS)
    # Persist hidden-base discovery from this step's encounter
    if encounter.get("base_discovered") and isinstance(encounter.get("hidden_base"), dict):
        bid = encounter["hidden_base"].get("id")
        if bid:
            mark_hidden_base_discovered(data, str(bid))
            # reload grid after mark
            grid = _rebuild_grid(data)
    flat = [c for row in grid for c in row]
    data["tiles"] = flat
    data["grid"] = grid
    _save_map_payload(data)
    view = full_map_view(data)
    view["travel"] = {
        "minutes": minutes,
        "steps": steps,
        "from": [px, py],
        "to": [x, y],
        "terrain": str(cell.get("state") or ""),
        "from_terrain": str((from_cell or {}).get("state") or ""),
        "on_road": str(cell.get("state") or "") in {"road", "bridge"},
        "settlement_id": settlement_id,
        "settlement": settlement_meta,
        "encounter": encounter,
        "seed": seed,
        "weather": weather_snapshot,
        "weather_mult": weather_mult,
        "base_discovered": bool(encounter.get("base_discovered")),
        "hidden_base": encounter.get("hidden_base"),
    }
    return view


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
