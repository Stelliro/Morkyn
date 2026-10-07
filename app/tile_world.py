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
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM world_presets WHERE id = ?",
            (preset_id,),
        ).fetchone()
        item = row_to_dict(row) if row else None
    finally:
        conn.close()
    if not item:
        return None
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
    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
        return rows_to_dicts(rows)
    finally:
        conn.close()


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
                        "scale": "board",
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
        pin_live_campaign_map(conn)
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
    payload["scale"] = "board"
    payload["map_role"] = "legacy"
    payload["legacy"] = True
    # Standing vision on spawn (radius 1, LOS-aware).
    mark_visited(payload, start[0], start[1], radius=DEFAULT_VISION_RADIUS, save=True)
    return payload


def generate_scaled_world(
    *,
    preset_id: str = "forest_march",
    seed: int | None = None,
    density_percent: int | None = None,
    notice_percent: int | None = None,
    assign_images: bool = False,
) -> dict[str, Any]:
    """Persist a 16,383 world. Tiles are not stored. assign_images is ignored on purpose."""
    del assign_images
    from app.world_scale import build_world, preview_window

    preset = get_world_preset(preset_id) or get_world_preset("frontier_any")
    if not preset:
        raise ValueError("No world presets available.")
    seed = int(seed if seed is not None else (time.time_ns() % (2**31 - 1)))
    world = build_world(preset, seed, density_percent, notice_percent)
    run_id = f"world-{seed}-{uuid.uuid4().hex[:8]}"
    world["id"] = run_id
    world["run_id"] = run_id
    player = world.get("player") or {}
    meta = {
        "scale": "world",
        "landmarks": [],
        "settlements_meta": world.get("settlements_meta") or [],
        "hidden_bases": [],
        "stats": world.get("stats") or {},
        "visited": world.get("visited") or [],
        "features": {},
        "knowledge": world.get("knowledge") or {},
        "place_anchors": {},
        "density_percent": world.get("density_percent"),
        "density_source": world.get("density_source") or "",
        "theme": world.get("theme") or "",
        "scale_plan": world.get("scale_plan") or {},
        "cities": world.get("cities") or [],
        "roads": world.get("roads") or [],
        "allows_slavery": bool(world.get("allows_slavery")),
        "revealed": list(world.get("revealed") or []),
        "notice_percent": world.get("notice_percent"),
        "notice_source": world.get("notice_source") or "",
        "terrain_bands": world.get("terrain_bands") if isinstance(world.get("terrain_bands"), dict) else {},
        "materials": list(world.get("materials") or []),
        "people_profile": world.get("people_profile") if isinstance(world.get("people_profile"), dict) else {},
    }
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO world_maps
              (id, preset_id, seed, width, height, age, environment, tiles_json, player_x, player_y, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                world.get("preset_id") or preset.get("id") or "",
                seed,
                int(world["width"]),
                int(world["height"]),
                world.get("age") or "",
                world.get("environment") or "",
                "[]",
                int(player.get("x") or 0),
                int(player.get("y") or 0),
                json.dumps(meta, ensure_ascii=True),
            ),
        )
        pin_live_campaign_map(conn)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_world_map_id', ?)",
            (run_id,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', ?)",
            (json.dumps(True),),
        )
        conn.commit()
    finally:
        conn.close()
    mark_visited(
        world,
        int(player.get("x") or 0),
        int(player.get("y") or 0),
        radius=DEFAULT_VISION_RADIUS,
        save=True,
    )
    preview = preview_window(world)
    world["preview"] = preview
    world["ascii"] = preview.get("ascii") or ""
    world["tiles"] = []
    world["grid"] = []
    world.pop("cell_index", None)
    return world


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


def get_map(map_id: str | None = None, conn=None) -> dict[str, Any] | None:
    def _read(connection):
        chosen = str(map_id or "")
        if not chosen:
            found = connection.execute(
                "SELECT value FROM settings WHERE key = 'active_world_map_id'"
            ).fetchone()
            chosen = str(found["value"]) if found else ""
        if not chosen:
            return None
        return connection.execute("SELECT * FROM world_maps WHERE id = ?", (chosen,)).fetchone()

    if conn is not None:
        row = _read(conn)
        item = row_to_dict(row) if row else None
    else:
        owned = connect()
        try:
            row = _read(owned)
            item = row_to_dict(row) if row else None
        finally:
            owned.close()
    if not item:
        return None
    tiles = json.loads(item.get("tiles_json") or "[]")
    meta = json.loads(item.get("meta_json") or "{}")
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    scale = str(meta.get("scale") or "")
    map_role = "world" if scale == "world" else "legacy"
    grid: list[list[dict[str, Any]]] = []
    if scale == "world":
        tiles = []
    elif width and height and len(tiles) == width * height:
        for y in range(height):
            grid.append(tiles[y * width : (y + 1) * width])
    loaded = {
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
        "place_anchors": meta.get("place_anchors") if isinstance(meta.get("place_anchors"), dict) else {},
        "run_id": item.get("id"),
        "created_at": item.get("created_at"),
        "scale": scale,
        "map_role": map_role,
        "legacy": map_role == "legacy",
        "cities": meta.get("cities") if isinstance(meta.get("cities"), list) else [],
        "roads": meta.get("roads") if isinstance(meta.get("roads"), list) else [],
        "density_percent": meta.get("density_percent"),
        "density_source": str(meta.get("density_source") or ""),
        "theme": str(meta.get("theme") or ""),
        "scale_plan": meta.get("scale_plan") if isinstance(meta.get("scale_plan"), dict) else {},
        "allows_slavery": bool(meta.get("allows_slavery")),
        "revealed": list(meta.get("revealed") or []) if isinstance(meta.get("revealed"), list) else [],
        "notice_percent": meta.get("notice_percent"),
        "notice_source": str(meta.get("notice_source") or ""),
        "terrain_bands": meta.get("terrain_bands") if isinstance(meta.get("terrain_bands"), dict) else {},
        "materials": list(meta.get("materials") or []) if isinstance(meta.get("materials"), list) else [],
        "people_profile": meta.get("people_profile") if isinstance(meta.get("people_profile"), dict) else {},
    }
    if scale == "world":
        from app.world_scale import index_cities

        loaded["cell_index"] = index_cities(loaded["cities"])
    return loaded


# The letter board the setup screen's Legacy button opens (static/app.js
# LEGACY_MAP_SEED). Not a campaign map, but pruning keeps it so that button
# still has something to show.
LEGACY_BOARD_SEED = 1935480396


def active_map_id(conn) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = 'active_world_map_id'").fetchone()
    value = str((row["value"] if row else "") or "").strip()
    if value.startswith('"'):
        try:
            value = str(json.loads(value) or "").strip()
        except (TypeError, ValueError):
            pass
    return value


# The map a campaign started on, recorded at Start. Opening New game rolls a
# fresh map and makes it active straight away, before Start; a player who
# then goes back and keeps playing the old game has an active map that is
# not that game's. Saves and pruning keep the pinned map too, so that stray
# roll can never cost a campaign its own map.
CAMPAIGN_MAP_KEY = "campaign_world_map_id"


def pinned_map_id(conn) -> str:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (CAMPAIGN_MAP_KEY,)).fetchone()
    except Exception:
        return ""
    value = str((row["value"] if row else "") or "").strip()
    if value.startswith('"'):
        try:
            value = str(json.loads(value) or "").strip()
        except (TypeError, ValueError):
            pass
    return value


def pin_campaign_map(conn) -> str:
    """Record the active map as this campaign's own (called at Start)."""
    chosen = active_map_id(conn)
    if not chosen or conn.execute("SELECT id FROM world_maps WHERE id = ?", (chosen,)).fetchone() is None:
        # No map to pin: the last game's pin must not ride into this one.
        conn.execute("DELETE FROM settings WHERE key = ?", (CAMPAIGN_MAP_KEY,))
        return ""
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (CAMPAIGN_MAP_KEY, chosen)
    )
    return chosen


def pin_live_campaign_map(conn) -> str:
    """Before a new roll takes over the active map, a live campaign keeps its own.

    A game started before maps were pinned (game 2 among them) has no pin; the
    first roll on the setup screen would otherwise leave it with no record of
    its map. Only while a campaign is set up and nothing is pinned yet.
    """
    if pinned_map_id(conn):
        return ""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'setup_complete'").fetchone()
    except Exception:
        return ""
    if not row or str(row[0] or "").strip().strip('"').lower() != "true":
        return ""
    chosen = active_map_id(conn)
    if not chosen or conn.execute("SELECT id FROM world_maps WHERE id = ?", (chosen,)).fetchone() is None:
        return ""
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (CAMPAIGN_MAP_KEY, chosen))
    return chosen


def campaign_map_ids(conn) -> set[str]:
    """Maps this campaign uses: the active map and the map it started on.

    Empty when the active map is missing: then nothing says which map is in
    use, and callers keep every map.
    """
    out: set[str] = set()
    for chosen in (active_map_id(conn), pinned_map_id(conn)):
        if not chosen:
            if not out:
                return set()
            continue
        row = conn.execute("SELECT id FROM world_maps WHERE id = ?", (chosen,)).fetchone()
        if row:
            out.add(chosen)
        elif not out:
            return set()
    return out


def legacy_board_ids(conn) -> set[str]:
    row = conn.execute(
        "SELECT id FROM world_maps WHERE seed = ? AND width = 36 AND height = 36 "
        "ORDER BY created_at DESC LIMIT 1",
        (LEGACY_BOARD_SEED,),
    ).fetchone()
    return {str(row["id"])} if row else set()


def campaign_map_rows(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The world_maps rows a campaign save carries: only the ones it uses.

    Playtest #25: every save copied the whole table (75 maps since July in
    game 2). With no usable active map the rows pass through unchanged,
    so a save never loses the map it would have needed.
    """
    keep = campaign_map_ids(conn)
    if not keep:
        return rows
    return [row for row in rows if str((row or {}).get("id") or "") in keep]


def prune_world_maps(conn) -> dict[str, Any]:
    """Delete stored maps this campaign does not use; returns what went.

    Called when a new game starts, after its map is rolled and active
    and pinned (``pin_campaign_map``). Keeps the campaign's maps and the
    Legacy button's board. Does nothing without an active map, since then
    there is no telling which is in use.
    """
    keep = campaign_map_ids(conn)
    if not keep:
        return {"removed": 0, "kept": [], "skipped": "no active map"}
    keep |= legacy_board_ids(conn)
    drop = [str(row["id"]) for row in conn.execute("SELECT id FROM world_maps").fetchall() if str(row["id"]) not in keep]
    for start in range(0, len(drop), 200):
        chunk = drop[start:start + 200]
        marks = ", ".join("?" for _ in chunk)
        conn.execute(f"DELETE FROM world_maps WHERE id IN ({marks})", chunk)
        try:
            conn.execute(f"DELETE FROM tile_image_run_disable WHERE run_id IN ({marks})", chunk)
        except Exception:
            pass
    # Town grid rows go with their map (docs/TownGrid.md 9).
    try:
        from app.town_grid import prune_town_rows

        prune_town_rows(conn, keep)
    except Exception:
        pass
    return {"removed": len(drop), "kept": sorted(keep)}


def get_legacy_map() -> dict[str, Any] | None:
    """Newest small stored board, not the active world.

    The setup screen used to open whichever map was active. Before world-sized
    maps, that was one of these boards. Does not change the active map.
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id
            FROM world_maps
            WHERE COALESCE(json_extract(meta_json, '$.scale'), '') != 'world'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    return get_map(str(rows[0]["id"]))


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


def _save_map_payload(map_data: dict[str, Any], conn=None) -> None:
    """Persist player position, visited, tiles back to world_maps.

    Pass the caller's connection when a turn transaction is already open.
    A second connection cannot write while that transaction holds the lock.
    """
    map_id = str(map_data.get("id") or "")
    if not map_id:
        return
    width = int(map_data.get("width") or 0)
    height = int(map_data.get("height") or 0)
    tiles = map_data.get("tiles") or []
    if not tiles and str(map_data.get("scale") or "") != "world":
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
        "place_anchors": map_data.get("place_anchors") if isinstance(map_data.get("place_anchors"), dict) else {},
        "revealed": list(map_data.get("revealed") or []),
    }
    if str(map_data.get("scale") or "") == "world":
        meta["scale"] = "world"
        meta["density_percent"] = map_data.get("density_percent")
        meta["density_source"] = map_data.get("density_source") or ""
        meta["theme"] = map_data.get("theme") or ""
        meta["scale_plan"] = map_data.get("scale_plan") or {}
        meta["cities"] = map_data.get("cities") or []
        meta["roads"] = map_data.get("roads") or []
        meta["allows_slavery"] = bool(map_data.get("allows_slavery"))
        meta["notice_percent"] = map_data.get("notice_percent")
        meta["notice_source"] = map_data.get("notice_source") or ""
        meta["terrain_bands"] = map_data.get("terrain_bands") if isinstance(map_data.get("terrain_bands"), dict) else {}
        meta["materials"] = list(map_data.get("materials") or [])
        meta["people_profile"] = map_data.get("people_profile") if isinstance(map_data.get("people_profile"), dict) else {}
    payload = (
        json.dumps(tiles, ensure_ascii=True),
        int(player.get("x") or 0),
        int(player.get("y") or 0),
        json.dumps(meta, ensure_ascii=True),
        map_id,
    )
    sql = """
        UPDATE world_maps
        SET tiles_json = ?, player_x = ?, player_y = ?, meta_json = ?
        WHERE id = ?
    """
    if conn is not None:
        conn.execute(sql, payload)
        return
    owned = connect()
    try:
        owned.execute(sql, payload)
        owned.commit()
    finally:
        owned.close()


# Terrain that stops line-of-sight past the first ridge (you can see the face, not past it).
SIGHT_BLOCKERS = frozenset({"mountain", "cliff", "volcano"})
# Default ground vision: Chebyshev radius 1 → player tile + immediate ring (no long scouting).
DEFAULT_VISION_RADIUS = 1
# One story turn may cross this many tiles. A world-scale map is 16,383 cells on a side.
STEP_BUDGET = 4
SETTLEMENT_HORIZON = 16
BLOCKED_STATES = frozenset({"void", "water", "lava", "cliff"})


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


def reveal_chart_area(
    map_data: dict[str, Any],
    *,
    radius: int,
    source: str = "map",
    conn=None,
) -> dict[str, Any]:
    """
    A map the player was given: the ground it shows is revealed on theirs.

    Terrain within ``radius`` (Chebyshev, around the player) joins the revealed
    tiles, and towns and landmarks in that square become known markers. The
    item itself is not kept: maps take no pack space and what they showed is
    never lost.
    """
    radius = max(1, min(24, int(radius)))
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    grid = _rebuild_grid(map_data)
    width = len(grid[0]) if grid else int(map_data.get("width") or 0)
    height = len(grid) if grid else int(map_data.get("height") or 0)
    visited = set(str(v) for v in (map_data.get("visited") or []))
    before = len(visited)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = px + dx, py + dy
            if 0 <= nx < width and 0 <= ny < height:
                visited.add(f"{nx},{ny}")
    map_data["visited"] = sorted(visited)

    settlement_ids: list[str] = []
    for sm in map_data.get("settlements_meta") or []:
        if not isinstance(sm, dict):
            continue
        sx, sy = int(sm.get("x") or 0), int(sm.get("y") or 0)
        if max(abs(sx - px), abs(sy - py)) <= radius:
            settlement_ids.append(str(sm.get("id") or f"{sx},{sy}"))
    notes: list[dict[str, Any]] = []
    for lm in map_data.get("landmarks") or []:
        if not isinstance(lm, dict):
            continue
        lx, ly = int(lm.get("x") or 0), int(lm.get("y") or 0)
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
    knowledge = grant_map_knowledge(map_data, settlement_ids=settlement_ids, notes=notes, source=source, save=False)
    _save_map_payload(map_data, conn)
    return {
        "ok": True,
        "radius": radius,
        "tiles_revealed": len(visited) - before,
        "settlements_known": len(settlement_ids),
        "landmarks_known": len(notes),
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


def _settlement_res(side: int, span: int) -> int:
    """Samples per cell edge: enough to read the wards, few enough to send a metropolis."""
    return max(1, min(int(side), max(12, 64 // max(1, int(span)))))


def settlement_view(
    map_data: dict[str, Any],
    *,
    city_id: str = "",
    places: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One settlement's own grid, read-only, drawn only as far as the player knows it.

    The world map's rules decide what is known: a settlement is listed once a
    tile of it was seen or someone told you of it. Inside it, a world cell shows
    its wards and streets only when that cell was seen; the rest is outline.
    Without ``city_id`` the settlement you stand in is chosen, else none.
    """
    if str(map_data.get("scale") or "") != "world" or not map_data.get("cities"):
        return {"available": False, "reason": "This map has no settlement grids.", "settlements": []}
    from app.world_scale import cell_raster, index_cities

    cities = {str(c.get("id") or ""): c for c in map_data.get("cities") or [] if isinstance(c, dict)}
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    index = map_data.get("cell_index")
    if not isinstance(index, dict):
        index = index_cities(list(cities.values()))
    here_entry = index.get(f"{px},{py}") or {}
    here_id = str((here_entry.get("city") or {}).get("id") or "")
    seen = {str(v) for v in (map_data.get("visited") or [])} | {str(v) for v in (map_data.get("revealed") or [])}
    seen.add(f"{px},{py}")
    known: list[dict[str, Any]] = []
    for item in filter_settlements_for_player(map_data):
        sid = str(item.get("id") or "")
        if sid in cities:
            known.append(
                {
                    "id": sid,
                    "name": str(cities[sid].get("name") or item.get("name") or "Settlement"),
                    "band": str(cities[sid].get("band") or ""),
                    "known_how": str(item.get("known_how") or ""),
                    "here": sid == here_id,
                }
            )
    if here_id and not any(k["id"] == here_id for k in known):
        city = cities[here_id]
        known.insert(0, {"id": here_id, "name": str(city.get("name") or "Settlement"),
                         "band": str(city.get("band") or ""), "known_how": "visited", "here": True})
    known_ids = {k["id"] for k in known}
    wanted = str(city_id or "").strip()
    if wanted and wanted not in known_ids:
        wanted = ""
    selected = wanted or here_id
    out: dict[str, Any] = {
        "available": True,
        "settlements": known,
        "selected": selected,
        "here": here_id,
        "settlement": None,
    }
    if not selected:
        out["reason"] = "You are not in a settlement you know." if known else "You know of no settlement yet."
        return out
    city = cities[selected]
    cells = [c for c in city.get("cells") or [] if isinstance(c, dict)]
    span = city.get("span") or [1, 1]
    span_w, span_h = max(1, int(span[0])), max(1, int(span[1]))
    drawn: list[dict[str, Any]] = []
    for cell in cells:
        cx, cy = int(cell.get("x") or 0), int(cell.get("y") or 0)
        local = cell.get("local") or [0, 0]
        side = max(1, int(cell.get("side") or 1))
        is_known = f"{cx},{cy}" in seen
        entry: dict[str, Any] = {
            "x": cx,
            "y": cy,
            "local": [int(local[0]), int(local[1])],
            "side": side,
            "known": is_known,
            "here": cx == px and cy == py,
        }
        if is_known:
            res = _settlement_res(side, max(span_w, span_h))
            entry["res"] = res
            entry["raster"] = cell_raster(cell, res)
            entry["districts"] = [
                {
                    "id": str(d.get("id") or ""),
                    "type": str(d.get("type") or ""),
                    "label": str(d.get("label") or d.get("type") or ""),
                    "name": str(d.get("name") or ""),
                    "anchor": [int((d.get("anchor") or [0, 0])[0]), int((d.get("anchor") or [0, 0])[1])],
                    "requires_entry": bool(d.get("requires_entry")),
                }
                for d in cell.get("districts") or []
                if isinstance(d, dict)
            ]
        drawn.append(entry)
    player = None
    if selected == here_id:
        cell = here_entry.get("cell") or {}
        side = max(1, int(cell.get("side") or 1))
        local = cell.get("local") or [0, 0]
        # The engine keeps no finer position than the world cell; its centre stands in.
        player = {"x": px, "y": py, "local": [int(local[0]), int(local[1])],
                  "fine_x": side // 2, "fine_y": side // 2, "side": side}
    out["settlement"] = {
        "id": selected,
        "name": str(city.get("name") or "Settlement"),
        "band": str(city.get("band") or ""),
        "span": [span_w, span_h],
        "cells": drawn,
        "known_cells": sum(1 for c in drawn if c["known"]),
        "player": player,
        "places": [
            p for p in (places or [])
            if isinstance(p, dict) and any(int(p.get("x", -1)) == c["x"] and int(p.get("y", -1)) == c["y"] for c in drawn)
        ],
    }
    return out


def settlement_places(map_data: dict[str, Any], conn) -> list[dict[str, Any]]:
    """Places the player has been, pinned to world cells, with the venues inside them.

    A row in ``locations`` exists only once the story reached it, so every one is
    known. Outdoor places carry their tile in ``place_anchors``; the place you
    stand in (or the outdoor place around the room you are in) sits on your tile.
    """
    from app.venues import hours_note, kind_label

    rows = [dict(r) for r in conn.execute(
        "SELECT id, code, name, parent_id, kind, open_minute, close_minute FROM locations"
    ).fetchall()]
    by_id = {int(r["id"]): r for r in rows}
    children: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        if int(r.get("parent_id") or 0):
            children.setdefault(int(r["parent_id"]), []).append(r)
    minute_row = conn.execute("SELECT value FROM pacing WHERE key = 'world_minute'").fetchone()
    try:
        minute = int(float(minute_row["value"])) if minute_row else 0
    except (TypeError, ValueError):
        minute = 0
    player_row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    current = int(player_row["current_location_id"] or 0) if player_row else 0
    current_root = current
    guard = 0
    while current_root and int((by_id.get(current_root) or {}).get("parent_id") or 0) and guard < 16:
        current_root = int(by_id[current_root]["parent_id"])
        guard += 1
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    pinned: dict[int, tuple[int, int]] = {}
    for r in rows:
        if int(r.get("parent_id") or 0):
            continue
        anchor = _anchor_at(map_data, str(r.get("code") or ""), str(r.get("name") or ""))
        if anchor and anchor.get("x") is not None:
            pinned[int(r["id"])] = (int(anchor["x"]), int(anchor["y"]))
    if current_root and current_root in by_id and current_root not in pinned:
        pinned[current_root] = (px, py)

    def _venues(parent: int, depth: int = 0) -> list[dict[str, Any]]:
        found = []
        for r in children.get(parent, []):
            kind = str(r.get("kind") or "")
            found.append(
                {
                    "code": str(r.get("code") or ""),
                    "name": str(r.get("name") or ""),
                    "kind": kind,
                    "label": kind_label(kind) if kind else "",
                    "hours": hours_note(r, minute) if kind else "",
                    "here": int(r["id"]) == current,
                    "venues": _venues(int(r["id"]), depth + 1) if depth < 4 else [],
                }
            )
        return found

    places = []
    for loc_id, (x, y) in pinned.items():
        r = by_id[loc_id]
        places.append(
            {
                "code": str(r.get("code") or ""),
                "name": str(r.get("name") or ""),
                "x": x,
                "y": y,
                "here": loc_id == current,
                "venues": _venues(loc_id),
            }
        )
    return places


def local_map_view(map_data: dict[str, Any], *, radius: int = 6) -> dict[str, Any]:
    """Remembered land around the journey, not a sliding window that forgets.

    Every visited tile stays in the payload, plus a one-tile in-bounds fringe of
    unknown ground so the edge of what you have seen stays visible. Tiles you
    have never reached are omitted. Nothing already in ``visited`` is removed.
    ``radius`` remains the standing-vision hint the client used to request; it
    no longer clips memory.
    """
    world_scale = str(map_data.get("scale") or "") == "world"
    grid = None if world_scale else _rebuild_grid(map_data)
    if world_scale:
        width = int(map_data.get("width") or 0)
        height = int(map_data.get("height") or 0)
    elif not grid:
        return {"empty": True, "tiles": [], "radius": radius, "memory": True}
    else:
        width = len(grid[0])
        height = len(grid)
    if width <= 0 or height <= 0:
        return {"empty": True, "tiles": [], "radius": radius, "memory": True}
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    radius = max(1, min(14, int(radius or 6)))
    before_visit = set(str(v) for v in (map_data.get("visited") or []))
    mark_visited(map_data, px, py, radius=DEFAULT_VISION_RADIUS, save=False)
    visited = set(str(v) for v in (map_data.get("visited") or []))
    if f"{px},{py}" not in visited:
        visited.add(f"{px},{py}")
        map_data["visited"] = sorted(visited)
    if visited != before_visit:
        _save_map_payload(map_data)
    revealed = {str(item) for item in (map_data.get("revealed") or [])}
    include = set(visited) | revealed
    fringe: set[str] = set()
    for key in include:
        try:
            vx, vy = (int(part) for part in key.split(",", 1))
        except (TypeError, ValueError):
            continue
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny = vx + dx, vy + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                nkey = f"{nx},{ny}"
                if nkey not in include:
                    fringe.add(nkey)
    markers = knowledge_markers_for_view(map_data)
    markers_by_pos = {
        f"{int(m.get('x') or 0)},{int(m.get('y') or 0)}": m
        for m in markers
        if m.get("x") is not None and m.get("y") is not None
    }
    art_cache: dict[str, dict[str, Any]] = {}
    run_id = str(map_data.get("run_id") or map_data.get("id") or "")

    def _art_for(state: str) -> dict[str, Any]:
        if state in art_cache:
            return art_cache[state]
        found: dict[str, Any] = {}
        try:
            img = pick_image_for_state(state, run_id=run_id)
            if img:
                found = img
        except Exception:
            found = {}
        art_cache[state] = found
        return found

    local: list[dict[str, Any]] = []

    def _key_xy(item: str) -> tuple[int, int] | None:
        try:
            xs, ys = item.split(",", 1)
            return int(xs), int(ys)
        except (TypeError, ValueError):
            return None

    ordered = sorted(
        (key for key in (include | fringe) if _key_xy(key) is not None),
        key=lambda item: ( _key_xy(item)[1], _key_xy(item)[0] ),
    )
    for key in ordered:
        x, y = (int(part) for part in key.split(",", 1))
        if not (0 <= x < width and 0 <= y < height):
            continue
        is_player = x == px and y == py
        is_visited = key in visited or is_player
        is_revealed = key in revealed and not is_visited
        known = is_visited or is_revealed
        base = _cell_at(map_data, x, y, grid) or {}
        cell: dict[str, Any] = {
            "x": x,
            "y": y,
            "rel_x": x - px,
            "rel_y": y - py,
            "visited": is_visited,
            "revealed": key in revealed,
            "is_player": is_player,
            "fog": not known,
            "in_circle": True,
        }
        marker = markers_by_pos.get(key)
        if marker:
            cell["marker"] = {
                "kind": marker.get("kind") or "note",
                "label": marker.get("label") or "",
                "source": marker.get("source") or "",
            }
        if known:
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
                img = _art_for(str(cell.get("state") or ""))
                if img:
                    cell["image_id"] = img.get("id")
                    cell["image_path"] = img.get("path") or ""
                    cell["image_data_url"] = img.get("data_url") or ""
        else:
            cell["state"] = "unknown"
            cell["walkable"] = None
            cell["is_settlement"] = bool(
                marker and str(marker.get("kind") or "") in {"settlement", "town", "city"}
            )
        local.append(cell)
    emitted = {f"{int(t['x'])},{int(t['y'])}" for t in local}
    known_settlements = [
        s
        for s in filter_settlements_for_player(map_data)
        if f"{int(s.get('x') or 0)},{int(s.get('y') or 0)}" in emitted
    ]
    return {
        "empty": False,
        "radius": radius,
        "vision_radius": DEFAULT_VISION_RADIUS,
        "shape": "circle",
        "follow_player": True,
        "memory": True,
        "player": {"x": px, "y": py},
        "width": width,
        "height": height,
        "bounds": {"width": width, "height": height},
        "tiles": local,
        "visited_count": len(visited),
        "revealed_count": len(revealed),
        "explored_tiles": len(visited),
        "tile_style": "pixel-16-32",
        "markers": markers,
        "settlements_nearby": known_settlements,
        "knowledge": _ensure_knowledge(map_data),
    }


def full_map_view(map_data: dict[str, Any]) -> dict[str, Any]:
    """Full map for the detailed overlay: pan around; fog hides unvisited terrain.

    Known settlements / danger from intel appear as markers on the fog.
    A world-scale map returns only remembered cells. It does not allocate the 16,383 grid.
    """
    if str(map_data.get("scale") or "") == "world":
        remembered = local_map_view(map_data, radius=1)
        remembered["shape"] = "full"
        remembered["follow_player"] = False
        return remembered
    grid = _rebuild_grid(map_data)
    width = int(map_data.get("width") or (len(grid[0]) if grid else 0))
    height = int(map_data.get("height") or len(grid))
    px = int((map_data.get("player") or {}).get("x") or 0)
    py = int((map_data.get("player") or {}).get("y") or 0)
    visited = set(str(v) for v in (map_data.get("visited") or []))
    revealed = {str(item) for item in (map_data.get("revealed") or [])}
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
            is_revealed = key in revealed and not is_visited
            known = is_visited or is_revealed
            base = cell if isinstance(cell, dict) else {"state": "?", "x": x, "y": y}
            c: dict[str, Any] = {
                "x": x,
                "y": y,
                "visited": is_visited,
                "revealed": key in revealed,
                "is_player": is_player,
                "fog": not known,
            }
            marker = markers_by_pos.get(key)
            if marker:
                c["marker"] = {
                    "kind": marker.get("kind") or "note",
                    "label": marker.get("label") or "",
                    "source": marker.get("source") or "",
                }
            if known:
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
        "revealed_count": len(revealed),
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


def _known_danger_near(map_data: dict[str, Any] | None, x: int, y: int, radius: int = 3) -> int:
    """How many danger markers the player already knows about within radius."""
    if not isinstance(map_data, dict):
        return 0
    knowledge = map_data.get("knowledge") if isinstance(map_data.get("knowledge"), dict) else {}
    count = 0
    for marker in knowledge.get("danger") or []:
        if not isinstance(marker, dict):
            continue
        try:
            if max(abs(int(marker.get("x")) - x), abs(int(marker.get("y")) - y)) <= radius:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


def _finish_travel_encounter(
    rolled: dict[str, Any],
    assessment: dict[str, Any],
    base_here: dict[str, Any] | None,
    x: int,
    y: int,
    minutes: int,
    state: str,
) -> dict[str, Any]:
    """Shape an encounters.roll_encounter result like the legacy travel payload."""
    happened = bool(rolled.get("happened"))
    kind = str(rolled.get("kind") or "none")
    discovered = False

    # Walking onto an undiscovered camp is how camps get found, so that beat
    # takes priority over whatever the terrain table would otherwise have
    # picked this step.
    if base_here and not base_here.get("discovered") and happened:
        kind = "hidden_base"
    if base_here and happened and (kind == "hidden_base" or not base_here.get("discovered")):
        discovered = True
        base_here = dict(base_here)
        base_here["discovered"] = True
        base_here["discovered_at"] = f"{x},{y}"

    hostile = bool(rolled.get("hostile_default"))
    if base_here and str(base_here.get("owner") or "") == "bandit" and kind == "hidden_base":
        hostile = True

    payload: dict[str, Any] = {
        "happened": happened,
        "kind": kind if happened else "none",
        # Legacy key: several callers and the UI still read `p`.
        "p": rolled.get("chance"),
        "chance": rolled.get("chance"),
        "roll": rolled.get("roll"),
        "terrain": state,
        "minutes": minutes,
        "danger": assessment.get("danger"),
        "danger_band": assessment.get("band"),
        "danger_environment": assessment.get("environment"),
        "danger_player_multiplier": assessment.get("player_multiplier"),
        "factors": assessment.get("factors") or [],
    }
    if not happened:
        payload["avoided"] = bool(rolled.get("avoided"))
        payload["avoided_kind"] = rolled.get("avoided_kind")
        payload["awareness"] = rolled.get("awareness")
        payload["hidden_base"] = base_here
        payload["base_discovered"] = False
        return payload

    payload.update(
        {
            "label": rolled.get("label"),
            "wary_not_evil": bool(rolled.get("wary_not_evil")) and not hostile,
            "hostile_default": hostile,
            "hidden_base": base_here,
            "base_discovered": discovered,
            "outcome_seed": rolled.get("outcome_seed") or 0,
            "participant_tier": rolled.get("participant_tier") or "nameless",
            "count": rolled.get("count"),
            "threat": rolled.get("threat"),
            "surprise": rolled.get("surprise"),
            "awareness": rolled.get("awareness"),
        }
    )
    return payload


def roll_travel_encounter(
    to_cell: dict[str, Any] | None,
    *,
    minutes: int,
    seed: int,
    turn: int = 0,
    hidden_bases: list[dict[str, Any]] | None = None,
    weather: dict[str, Any] | None = None,
    world_time: dict[str, Any] | None = None,
    map_data: dict[str, Any] | None = None,
    settlement: dict[str, Any] | None = None,
    on_road: bool = False,
) -> dict[str, Any]:
    """
    Roll whether this step turns into an event, and what kind.

    Terrain still sets the baseline, but the actual chance now runs through
    :func:`app.encounters.assess_danger`, so the player's stats, skills,
    fatigue, wounds, carried load, notoriety, local standing and the clock all
    move the number. Weather and terrain alone made a dying novice exactly as
    safe as a rested scout on the same tile.

    Return shape is unchanged for existing callers; the extra ``danger``,
    ``factors``, ``awareness`` and ``count`` keys are additive.
    """
    state = str((to_cell or {}).get("state") or "plains").lower()
    x = int((to_cell or {}).get("x") or 0)
    y = int((to_cell or {}).get("y") or 0)

    base_here = None
    for b in hidden_bases or []:
        if not isinstance(b, dict):
            continue
        if int(b.get("x") or -1) == x and int(b.get("y") or -1) == y:
            base_here = b
            break

    try:
        from app import encounters as encounters_mod
        from app.skill_checks import player_with_gear_scores

        snapshot = encounters_mod.player_snapshot()
        if world_time is None:
            from app.world import get_world_time

            world_time = get_world_time()
        aware = player_with_gear_scores(snapshot.get("player"))
        assessment = encounters_mod.assess_danger(
            terrain=state,
            weather=weather,
            world_time=world_time,
            player=aware,
            skills=snapshot.get("skills"),
            resources=snapshot.get("resources"),
            inventory_summary=snapshot.get("inventory_summary"),
            options=snapshot.get("options"),
            settlement=settlement,
            known_danger_nearby=_known_danger_near(map_data, x, y),
            area_reputation=int(snapshot.get("area_reputation") or 0),
            on_road=bool(on_road) or state in {"road", "bridge"},
            hidden_base_here=bool(base_here and not base_here.get("discovered")),
        )
        rolled = encounters_mod.roll_encounter(
            assessment,
            minutes=minutes,
            seed=seed,
            turn=turn,
            player=aware,
            skills=snapshot.get("skills"),
            options=snapshot.get("options"),
        )
        return _finish_travel_encounter(rolled, assessment, base_here, x, y, minutes, state)
    except Exception:
        # Never let the danger model stop someone from walking.
        pass

    # --- legacy fallback: terrain + weather only ------------------------------
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
    rng = random.Random((int(seed) ^ (int(turn or 0) * 2654435761)) & 0x7FFFFFFF)
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
    # The pacing turn goes into the roll as well. Once the surrounding tiles
    # are revealed, len(visited) stops moving, and this seed alone replayed
    # the identical natural, kind, count and awareness d20 on every retrace
    # of the same step: one extreme roll made a step a permanent ambush or
    # permanently quiet while danger still moved with night, weather and
    # fatigue. The same turn still seeds the same roll, which rewind needs.
    try:
        with connect() as _turn_conn:
            _turn_row = _turn_conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        travel_turn = int(_turn_row["value"]) if _turn_row else 0
    except Exception:
        travel_turn = 0
    settlement_id = cell.get("settlement_id")
    settlement_meta = None
    if settlement_id:
        for sm in data.get("settlements_meta") or []:
            if str(sm.get("id")) == str(settlement_id):
                settlement_meta = sm
                break

    encounter = roll_travel_encounter(
        {**cell, "x": x, "y": y},
        minutes=minutes,
        seed=seed,
        turn=travel_turn,
        hidden_bases=list(data.get("hidden_bases") or []),
        weather=weather_snapshot,
        map_data=data,
        settlement=settlement_meta,
        on_road=str(cell.get("state") or "") in {"road", "bridge"},
    )

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
        from app.world_scale import art_look_for, materials_for

        look = art_look_for(str(preset.get("id") or preset_id))
        mats = materials_for(str(preset.get("id") or preset_id))
        if look:
            bits.append(look)
        if mats:
            bits.append("materials: " + ", ".join(mats))
    return ", ".join(bits)


# ---------------------------------------------------------------------------
# Story walks: the generated grid is the whole land, and a turn crosses few tiles.
# ---------------------------------------------------------------------------

_DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "northeast": (1, -1),
    "east": (1, 0),
    "southeast": (1, 1),
    "south": (0, 1),
    "southwest": (-1, 1),
    "west": (-1, 0),
    "northwest": (-1, -1),
}
_DIRECTION_COMPACT = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
    "north": "north",
    "south": "south",
    "east": "east",
    "west": "west",
    "northeast": "northeast",
    "northwest": "northwest",
    "southeast": "southeast",
    "southwest": "southwest",
}
_DIRECTION_RE = re.compile(
    r"\b(north[\s-]?east|north[\s-]?west|south[\s-]?east|south[\s-]?west|"
    r"northeast|northwest|southeast|southwest|north|south|east|west)\b",
    re.I,
)
# Clockwise from north. Fallback steps use the first walkable tile in this order.
NEIGHBOR_ORDER: tuple[tuple[str, int, int], ...] = tuple(
    (name, _DIRECTIONS[name][0], _DIRECTIONS[name][1]) for name in (
        "north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest",
    )
)
_GENERIC_PLACE_LABELS = frozenset({
    "town", "city", "village", "harbor", "colony", "station", "ruins", "dungeon",
    "settlement", "landmark", "road", "camp",
})


def canonical_direction(text: str) -> str:
    raw = re.sub(r"[\s_\-]+", "", str(text or "").strip().lower())
    return _DIRECTION_COMPACT.get(raw, "")


def clamp_steps(value: Any, default: int = STEP_BUDGET) -> int:
    if value is None or value == "":
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(STEP_BUDGET, n))


def direction_in_text(text: str) -> str:
    match = _DIRECTION_RE.search(str(text or ""))
    if not match:
        return ""
    return canonical_direction(match.group(1))


def heading_name(dx: int, dy: int) -> str:
    if dx == 0 and dy == 0:
        return ""
    ax, ay = abs(int(dx)), abs(int(dy))
    sx = 0 if dx == 0 else (1 if dx > 0 else -1)
    sy = 0 if dy == 0 else (1 if dy > 0 else -1)
    if ax > ay * 2:
        sy = 0
    elif ay > ax * 2:
        sx = 0
    for name, (hx, hy) in _DIRECTIONS.items():
        if hx == sx and hy == sy:
            return name
    return ""


def tile_walkable(cell: dict[str, Any] | None) -> bool:
    if not isinstance(cell, dict):
        return False
    if str(cell.get("state") or "") in BLOCKED_STATES:
        return False
    return bool(cell.get("walkable", True))


def _player_xy(map_data: dict[str, Any]) -> tuple[int, int]:
    player = map_data.get("player") or {}
    return int(player.get("x") or 0), int(player.get("y") or 0)


def _walk_report(
    map_data: dict[str, Any],
    *,
    direction: str,
    requested: int,
    taken: int,
    stopped: str,
    start: tuple[int, int],
    end: tuple[int, int],
) -> dict[str, Any]:
    return {
        "ok": True,
        "direction": direction,
        "steps_requested": requested,
        "steps_taken": taken,
        "stopped": stopped,
        "from": [start[0], start[1]],
        "to": [end[0], end[1]],
        "visited_count": len(map_data.get("visited") or []),
    }


def _cell_at(
    map_data: dict[str, Any],
    x: int,
    y: int,
    grid: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any] | None:
    """One cell. World-scale maps sample the seed instead of indexing a stored grid."""
    if str(map_data.get("scale") or "") == "world":
        from app.world_scale import world_cell

        return world_cell(map_data, x, y)
    if grid is None:
        grid = _rebuild_grid(map_data)
    if not grid:
        return None
    height = len(grid)
    width = len(grid[0]) if height else 0
    if not (0 <= int(x) < width and 0 <= int(y) < height):
        return None
    cell = grid[int(y)][int(x)]
    return cell if isinstance(cell, dict) else None


def walk_steps(map_data: dict[str, Any], direction: str, steps: Any, *, save: bool = False) -> dict[str, Any]:
    """Step one tile at a time. Stop at the edge or at ground you cannot cross.

    Visited tiles are only added. A blocked step leaves the token and the memory where they were.
    """
    heading = canonical_direction(direction)
    dx, dy = _DIRECTIONS.get(heading, (0, 0))
    budget = clamp_steps(steps)
    start = _player_xy(map_data)
    if not heading:
        return _walk_report(
            map_data, direction="", requested=budget, taken=0, stopped="bad_direction", start=start, end=start,
        )
    grid = None if str(map_data.get("scale") or "") == "world" else _rebuild_grid(map_data)
    if grid:
        height = len(grid)
        width = len(grid[0]) if height else 0
    else:
        width = int(map_data.get("width") or 0)
        height = int(map_data.get("height") or 0)
    if width <= 0 or height <= 0:
        return _walk_report(
            map_data, direction=heading, requested=budget, taken=0, stopped="no_grid", start=start, end=start,
        )
    px, py = start
    taken = 0
    stopped = ""
    for _ in range(budget):
        nx, ny = px + dx, py + dy
        if not (0 <= nx < width and 0 <= ny < height):
            stopped = "edge"
            break
        if not tile_walkable(_cell_at(map_data, nx, ny, grid)):
            stopped = "blocked"
            break
        px, py = nx, ny
        map_data["player"] = {"x": px, "y": py}
        mark_visited(map_data, px, py, radius=DEFAULT_VISION_RADIUS, save=False)
        taken += 1
    if not stopped:
        stopped = "budget" if taken else "none"
    if save and taken:
        _save_map_payload(map_data)
    return _walk_report(
        map_data, direction=heading, requested=budget, taken=taken, stopped=stopped, start=start, end=(px, py),
    )


def walk_toward(
    map_data: dict[str, Any],
    tx: int,
    ty: int,
    *,
    budget: int = STEP_BUDGET,
    save: bool = False,
) -> dict[str, Any]:
    """Greedy walk that reduces Chebyshev distance. Stop when the next step cannot."""
    budget = clamp_steps(budget)
    start = _player_xy(map_data)
    grid = None if str(map_data.get("scale") or "") == "world" else _rebuild_grid(map_data)
    if grid:
        height = len(grid)
        width = len(grid[0]) if height else 0
    else:
        width = int(map_data.get("width") or 0)
        height = int(map_data.get("height") or 0)
    if width <= 0 or height <= 0:
        return _walk_report(
            map_data, direction="", requested=budget, taken=0, stopped="no_grid", start=start, end=start,
        )
    px, py = start
    tx, ty = int(tx), int(ty)
    taken = 0
    stopped = ""
    while taken < budget and (px != tx or py != ty):
        here = max(abs(tx - px), abs(ty - py))
        options: list[tuple[int, int, int, int, int]] = []
        for _name, dx, dy in NEIGHBOR_ORDER:
            nx, ny = px + dx, py + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            cell = _cell_at(map_data, nx, ny, grid)
            if not tile_walkable(cell):
                continue
            cheb = max(abs(tx - nx), abs(ty - ny))
            if cheb >= here:
                continue
            manh = abs(tx - nx) + abs(ty - ny)
            road = 0 if str((cell or {}).get("state") or "") in {"road", "bridge"} else 1
            options.append((cheb, manh, road, nx, ny))
        if not options:
            stopped = "blocked"
            break
        options.sort()
        _cheb, _manh, _road, nx, ny = options[0]
        px, py = nx, ny
        map_data["player"] = {"x": px, "y": py}
        mark_visited(map_data, px, py, radius=DEFAULT_VISION_RADIUS, save=False)
        taken += 1
    if not stopped:
        stopped = "arrived" if (px == tx and py == ty) else "budget"
    direction = heading_name(px - start[0], py - start[1])
    if save and taken:
        _save_map_payload(map_data)
    return _walk_report(
        map_data, direction=direction, requested=budget, taken=taken, stopped=stopped, start=start, end=(px, py),
    )


def remember_place(
    map_data: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
    x: int,
    y: int,
    parent_id: int = 0,
) -> None:
    """Pin an outdoor place to a tile. An existing pin does not move, and a room is not pinned."""
    if int(parent_id or 0):
        return
    code_s = str(code or "").strip()
    name_s = str(name or "").strip()
    if not code_s and not name_s:
        return
    anchors = map_data.get("place_anchors")
    if not isinstance(anchors, dict):
        anchors = {}
        map_data["place_anchors"] = anchors
    existing = None
    if code_s and code_s.upper() in anchors:
        existing = anchors.get(code_s.upper())
    elif name_s and name_s.lower() in anchors:
        existing = anchors.get(name_s.lower())
    if isinstance(existing, dict) and existing.get("x") is not None:
        return
    record = {"code": code_s, "name": name_s, "x": int(x), "y": int(y)}
    if code_s:
        anchors[code_s.upper()] = record
    if name_s:
        anchors[name_s.lower()] = record


def _anchor_at(map_data: dict[str, Any], code: str, name: str) -> dict[str, Any] | None:
    anchors = map_data.get("place_anchors")
    if not isinstance(anchors, dict):
        return None
    if code and isinstance(anchors.get(str(code).upper()), dict):
        return anchors[str(code).upper()]
    if name and isinstance(anchors.get(str(name).strip().lower()), dict):
        return anchors[str(name).strip().lower()]
    return None


def _place_names(dest: dict[str, Any] | None, movement_report: dict[str, Any] | None) -> list[str]:
    names: list[str] = []
    for value in (
        (dest or {}).get("name"),
        (dest or {}).get("code"),
        (movement_report or {}).get("destination"),
        # A venue stands on its parent's tile (playtest #33).
        (dest or {}).get("parent_name"),
        (dest or {}).get("parent_code"),
    ):
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)
    return names


def _names_match(want: str, label: str) -> bool:
    left = str(want or "").strip().lower()
    right = str(label or "").strip().lower()
    if not left or not right:
        return False
    if right in _GENERIC_PLACE_LABELS and left != right:
        return False
    if left == right:
        return True
    return len(right) >= 4 and (right in left or left in right)


def _settlement_match(map_data: dict[str, Any], names: list[str], px: int, py: int) -> tuple[int, int] | None:
    best: tuple[int, int, int] | None = None
    for settlement in list_settlements(map_data):
        label = str(settlement.get("name") or "")
        if not any(_names_match(name, label) for name in names):
            continue
        try:
            sx, sy = int(settlement.get("x")), int(settlement.get("y"))
        except (TypeError, ValueError):
            continue
        cheb = max(abs(sx - px), abs(sy - py))
        if cheb > SETTLEMENT_HORIZON:
            continue
        if best is None or cheb < best[0]:
            best = (cheb, sx, sy)
    if best is None or best[0] == 0:
        return None
    return best[1], best[2]


def _nearest_other_settlement(map_data: dict[str, Any], px: int, py: int) -> tuple[int, int] | None:
    found = _nearest_settlement_info(map_data, px, py)
    return (found[0], found[1]) if found else None


def _nearest_settlement_info(map_data: dict[str, Any], px: int, py: int) -> tuple[int, int, str] | None:
    best: tuple[int, int, int, str] | None = None
    for settlement in list_settlements(map_data):
        try:
            sx, sy = int(settlement.get("x")), int(settlement.get("y"))
        except (TypeError, ValueError):
            continue
        cheb = max(abs(sx - px), abs(sy - py))
        if cheb == 0 or cheb > SETTLEMENT_HORIZON:
            continue
        if best is None or cheb < best[0]:
            best = (cheb, sx, sy, str(settlement.get("name") or ""))
    if best is None:
        return None
    return best[1], best[2], best[3]


def _open_heading(map_data: dict[str, Any]) -> str:
    """The first road (else open) neighbour of the player's tile, or ""."""
    px, py = _player_xy(map_data)
    grid = _rebuild_grid(map_data)
    height = len(grid)
    width = len(grid[0]) if height else 0
    roads: list[str] = []
    opens: list[str] = []
    for name, dx, dy in NEIGHBOR_ORDER:
        nx, ny = px + dx, py + dy
        if not (0 <= nx < width and 0 <= ny < height):
            continue
        cell = grid[ny][nx] if isinstance(grid[ny][nx], dict) else None
        if not tile_walkable(cell):
            continue
        if str((cell or {}).get("state") or "") in {"road", "bridge"}:
            roads.append(name)
        else:
            opens.append(name)
    return roads[0] if roads else (opens[0] if opens else "")


def place_bearings(map_data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Direction and distance from the player's tile to every pinned place, keyed by lower-case name.

    Playtest #33 (live): the draft was given known places as bare names, chose
    "east" for a walk back to the garage, and the map then walked west. The
    engine knows where each pinned place lies, so it says so before the model
    writes.
    """
    if not isinstance(map_data, dict):
        return {}
    anchors = map_data.get("place_anchors")
    if not isinstance(anchors, dict):
        return {}
    px, py = _player_xy(map_data)
    out: dict[str, dict[str, Any]] = {}
    for record in anchors.values():
        if not isinstance(record, dict) or record.get("x") is None:
            continue
        name = str(record.get("name") or "").strip()
        if not name or name.lower() in out:
            continue
        try:
            ax, ay = int(record["x"]), int(record["y"])
        except (TypeError, ValueError, KeyError):
            continue
        distance = max(abs(ax - px), abs(ay - py))
        if distance == 0:
            continue
        out[name.lower()] = {"name": name, "direction": heading_name(ax - px, ay - py), "distance": distance}
    return out


def default_heading(map_data: dict[str, Any] | None) -> dict[str, str]:
    """The way a walk with no direction and no pinned destination goes: the same
    choice the map walk's fallback makes, decided before the draft writes."""
    if not isinstance(map_data, dict):
        return {}
    px, py = _player_xy(map_data)
    try:
        found = _nearest_settlement_info(map_data, px, py)
    except Exception:
        found = None
    if found is not None:
        direction = heading_name(found[0] - px, found[1] - py)
        if direction:
            return {"direction": direction, "toward": found[2]}
    if str(map_data.get("scale") or "") == "world":
        return {}
    try:
        heading = _open_heading(map_data)
    except Exception:
        heading = ""
    return {"direction": heading, "toward": ""} if heading else {}


def _anchor_named_in(map_data: dict[str, Any], text: str) -> dict[str, Any] | None:
    """The pinned place the player's own words name (longest name wins), or None."""
    anchors = map_data.get("place_anchors")
    low = str(text or "").lower()
    if not isinstance(anchors, dict) or not low:
        return None
    best: dict[str, Any] | None = None
    for record in anchors.values():
        if not isinstance(record, dict) or record.get("x") is None:
            continue
        name = str(record.get("name") or "").strip().lower()
        if len(name) < 4 or name in _GENERIC_PLACE_LABELS:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", low):
            if best is None or len(name) > len(str(best.get("name") or "")):
                best = record
    return best


def _same_place(origin: dict[str, Any] | None, dest: dict[str, Any] | None) -> bool:
    if not origin or not dest:
        return True
    oid = int(origin.get("id") or 0)
    did = int(dest.get("id") or 0)
    if oid and did:
        return oid == did
    oc = str(origin.get("code") or "").upper()
    dc = str(dest.get("code") or "").upper()
    return bool(oc) and oc == dc


_DOORWAY_RE = re.compile(
    r"\b(?:step|go|walk|head|slip|duck|come|move)\s+(?:back\s+)?(?:into|inside|in)\b"
    r"|\benter(?:s|ed|ing)?\b"
    r"|\b(?:exit|leave|leaving)\s+(?:the\s+)?(?:shop|room|inn|tavern|watchhouse|building|house|hall|door)\b"
    r"|\b(?:go|step|walk|head)\s+(?:back\s+)?(?:out|outside)\b",
    re.I,
)


def _hike_despite_door(player_input: str) -> bool:
    """A journey still crosses ground when the scene happens to stop indoors.

    Stepping into a room does not. A compass direction does, even in the same sentence.
    """
    text = str(player_input or "")
    if direction_in_text(text):
        return True
    if _DOORWAY_RE.search(text):
        return False
    return True


def _is_door(origin: dict[str, Any] | None, dest: dict[str, Any] | None) -> bool:
    """Entering, leaving, or crossing between rooms of the same outdoor place."""
    if _same_place(origin, dest):
        return False
    op = int((origin or {}).get("parent_id") or 0)
    dp = int((dest or {}).get("parent_id") or 0)
    oid = int((origin or {}).get("id") or 0)
    did = int((dest or {}).get("id") or 0)
    if dp and oid and dp == oid:
        return True
    if op and did and op == did:
        return True
    if op and dp and op == dp:
        return True
    return False


def _direction_from_inputs(
    player_input: str,
    movement_report: dict[str, Any] | None,
    dest: dict[str, Any] | None,
) -> str:
    for text in (
        player_input,
        str((movement_report or {}).get("destination") or ""),
        str((dest or {}).get("name") or ""),
    ):
        found = direction_in_text(text)
        if found:
            return found
    return ""


def normalize_map_walk(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    direction = canonical_direction(str(raw.get("direction") or ""))
    if not direction:
        return None
    steps = raw.get("steps")
    return {"direction": direction, "steps": clamp_steps(steps if steps is not None else STEP_BUDGET)}


def plan_story_walk(
    map_data: dict[str, Any],
    *,
    player_input: str = "",
    input_kind: str = "player",
    movement_report: dict[str, Any] | None = None,
    map_walk: Any = None,
    origin: dict[str, Any] | None = None,
    dest: dict[str, Any] | None = None,
    travel: bool = False,
    town: bool = False,
) -> dict[str, Any]:
    """Decide whether this turn steps the grid. Does not move the token.

    ``town``: the player is inside a plotted town and the town rules moved (or
    kept) them this turn, so the world token stays on the town cell, explicit
    WALK included (docs/TownGrid.md 5.1).
    """
    if town:
        return {"action": "skip", "reason": "town"}
    explicit = normalize_map_walk(map_walk)
    if explicit:
        return {
            "action": "steps",
            "direction": explicit["direction"],
            "steps": explicit["steps"],
            "reason": "explicit",
        }
    if str(input_kind or "player") != "player":
        return {"action": "skip", "reason": "not_player"}
    if _is_door(origin, dest) and not (travel and _hike_despite_door(player_input)):
        return {"action": "skip", "reason": "door"}
    report = movement_report if isinstance(movement_report, dict) else {}
    status = str(report.get("status") or "")
    outdoor = status in {"model", "repaired"} and not _same_place(origin, dest)
    if outdoor:
        px, py = _player_xy(map_data)
        names = _place_names(dest, report)
        for name in names:
            anchor = _anchor_at(map_data, name if re.fullmatch(r"L\d+", name, re.I) else "", name)
            if anchor is None and re.fullmatch(r"L\d+", name, re.I):
                anchor = _anchor_at(map_data, name, "")
            if isinstance(anchor, dict):
                ax, ay = int(anchor.get("x") or 0), int(anchor.get("y") or 0)
                if (ax, ay) != (px, py):
                    return {"action": "toward", "x": ax, "y": ay, "reason": "outdoor_anchor"}
        settlement = _settlement_match(map_data, names, px, py)
        if settlement is not None:
            return {"action": "toward", "x": settlement[0], "y": settlement[1], "reason": "outdoor_anchor"}
        direction = _direction_from_inputs(player_input, report, dest)
        if direction:
            return {"action": "steps", "direction": direction, "steps": STEP_BUDGET, "reason": "outdoor_direction"}
        # A known place the player named: the bearing the draft was given (playtest #33).
        named = _anchor_named_in(map_data, player_input)
        if named is not None and (int(named["x"]), int(named["y"])) != (px, py):
            return {"action": "toward", "x": int(named["x"]), "y": int(named["y"]), "reason": "input_anchor"}
        return {"action": "fallback", "reason": "outdoor_fallback"}
    direction = _direction_from_inputs(player_input, report, dest)
    if direction and (travel or status == "unresolved"):
        return {"action": "steps", "direction": direction, "steps": STEP_BUDGET, "reason": "unresolved_direction"}
    return {"action": "skip", "reason": "no_step"}


def _fallback_step(map_data: dict[str, Any]) -> dict[str, Any]:
    px, py = _player_xy(map_data)
    target = _nearest_other_settlement(map_data, px, py)
    if target is not None:
        return walk_toward(map_data, target[0], target[1], budget=STEP_BUDGET, save=False)
    heading = _open_heading(map_data)
    if not heading:
        start = (px, py)
        return _walk_report(
            map_data, direction="", requested=1, taken=0, stopped="blocked", start=start, end=start,
        )
    return walk_steps(map_data, heading, 1, save=False)


def walk_journal_line(report: dict[str, Any]) -> str:
    steps = int(report.get("steps_taken") or 0)
    if steps <= 0:
        return ""
    to = report.get("to") or [0, 0]
    direction = str(report.get("direction") or "")
    if not direction:
        frm = report.get("from") or to
        direction = heading_name(int(to[0]) - int(frm[0]), int(to[1]) - int(frm[1]))
    word = "tile" if steps == 1 else "tiles"
    return (
        f"Walked {direction} {steps} {word} to ({int(to[0])},{int(to[1])}). "
        f"The map remembers {int(report.get('visited_count') or 0)} tiles."
    )


def apply_story_map_walk(
    map_data: dict[str, Any],
    *,
    player_input: str = "",
    input_kind: str = "player",
    movement_report: dict[str, Any] | None = None,
    map_walk: Any = None,
    origin: dict[str, Any] | None = None,
    dest: dict[str, Any] | None = None,
    travel: bool = False,
    save: bool = False,
    town: bool = False,
) -> dict[str, Any]:
    """Move the token for one story turn and pin outdoor places to the tiles they occupy."""
    plan = plan_story_walk(
        map_data,
        player_input=player_input,
        input_kind=input_kind,
        movement_report=movement_report,
        map_walk=map_walk,
        origin=origin,
        dest=dest,
        travel=travel,
        town=town,
    )
    if plan.get("action") == "skip":
        return {"status": "skipped", "reason": plan.get("reason") or "no_step", "steps_taken": 0}
    start = _player_xy(map_data)
    if origin and not int(origin.get("parent_id") or 0):
        remember_place(
            map_data,
            code=str(origin.get("code") or ""),
            name=str(origin.get("name") or ""),
            x=start[0],
            y=start[1],
            parent_id=0,
        )
    action = plan.get("action")
    if action == "steps":
        report = walk_steps(map_data, str(plan.get("direction") or ""), plan.get("steps") or STEP_BUDGET, save=False)
    elif action == "toward":
        report = walk_toward(map_data, int(plan.get("x") or 0), int(plan.get("y") or 0), save=False)
    else:
        report = _fallback_step(map_data)
    end = _player_xy(map_data)
    moved_place = not _same_place(origin, dest)
    if int(report.get("steps_taken") or 0) and moved_place and dest and not int(dest.get("parent_id") or 0):
        remember_place(
            map_data,
            code=str(dest.get("code") or ""),
            name=str(dest.get("name") or ""),
            x=end[0],
            y=end[1],
            parent_id=0,
        )
    report["status"] = "walked" if int(report.get("steps_taken") or 0) else "blocked"
    report["reason"] = plan.get("reason") or ""
    report["journal"] = walk_journal_line(report)
    if save and (int(report.get("steps_taken") or 0) or map_data.get("place_anchors")):
        _save_map_payload(map_data)
    return report


def spatial_contract(map_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """The finite land the story model is allowed to walk this turn."""
    if not isinstance(map_data, dict):
        return None
    world_scale = str(map_data.get("scale") or "") == "world"
    grid = None if world_scale else _rebuild_grid(map_data)
    if world_scale:
        width = int(map_data.get("width") or 0)
        height = int(map_data.get("height") or 0)
    elif not grid:
        return None
    else:
        height = len(grid)
        width = len(grid[0]) if height else 0
    if width <= 0 or height <= 0:
        return None
    px, py = _player_xy(map_data)
    px = min(max(px, 0), max(0, width - 1))
    py = min(max(py, 0), max(0, height - 1))
    here = _cell_at(map_data, px, py, grid) or {}
    exits: dict[str, dict[str, Any]] = {}
    for name, dx, dy in NEIGHBOR_ORDER:
        nx, ny = px + dx, py + dy
        if not (0 <= nx < width and 0 <= ny < height):
            exits[name] = {"status": "edge"}
            continue
        cell = _cell_at(map_data, nx, ny, grid) or {}
        terrain = str(cell.get("state") or "")
        if tile_walkable(cell):
            exits[name] = {"status": "walkable", "terrain": terrain}
        else:
            exits[name] = {"status": "blocked", "terrain": terrain}
    places: list[dict[str, Any]] = []
    seen: set[str] = set()
    if world_scale:
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for city in map_data.get("cities") or []:
            if not isinstance(city, dict):
                continue
            try:
                sx, sy = int(city.get("x")), int(city.get("y"))
            except (TypeError, ValueError):
                continue
            cheb = max(abs(sx - px), abs(sy - py))
            label = str(city.get("name") or "city")
            if cheb == 0 or not label.strip() or label.strip().lower() in seen:
                continue
            ranked.append((cheb, label, city))
        ranked.sort(key=lambda item: (item[0], item[1]))
        for cheb, label, city in ranked[:6]:
            seen.add(label.strip().lower())
            places.append(
                {
                    "name": label,
                    "direction": heading_name(int(city["x"]) - px, int(city["y"]) - py),
                    "distance": cheb,
                    "x": int(city["x"]),
                    "y": int(city["y"]),
                    "band": city.get("band") or "",
                }
            )
    for settlement in ([] if world_scale else list_settlements(map_data)):
        try:
            sx, sy = int(settlement.get("x")), int(settlement.get("y"))
        except (TypeError, ValueError):
            continue
        cheb = max(abs(sx - px), abs(sy - py))
        if cheb == 0 or cheb > SETTLEMENT_HORIZON:
            continue
        label = str(settlement.get("name") or settlement.get("state") or "place")
        key = label.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        places.append(
            {
                "name": label,
                "direction": heading_name(sx - px, sy - py),
                "distance": cheb,
                "x": sx,
                "y": sy,
            }
        )
    places.sort(key=lambda item: (int(item["distance"]), str(item["name"])))
    places = places[:6]
    explored = len(map_data.get("visited") or [])
    rule = (
        f"The land is this fixed {width}×{height} map. You are on tile ({px},{py}). "
        f"One turn walks at most {STEP_BUDGET} tiles, using WALK <direction> STEPS <1-{STEP_BUDGET}>. "
        "Directions are north, south, east, west, and the compounds. "
        "Stop at exits marked edge or blocked. "
        "MOVE names the place the scene stops in, inside this walk. "
        "Do not invent countryside past the step budget or the map edge. "
        "A shop, inn, or room entered from the current place is a door, not a hike."
    )
    if world_scale:
        rule += (
            " Each step is one world cell. A city is at most 9 by 9 connected cells, "
            "not a one-cell-wide line or a solid square, and each of those cells has an internal grid of at most 128 by 128. "
            "One step does not cross the streets inside a city."
        )
    payload = {
        "width": width,
        "height": height,
        "player": {"x": px, "y": py, "terrain": str(here.get("state") or "")},
        "step_budget": STEP_BUDGET,
        "exits": exits,
        "places_in_reach": places,
        "explored_tiles": explored,
        "rule": rule,
    }
    # The engine's own bearings, for the movement contract (playtest #33).
    bearings = place_bearings(map_data)
    if bearings:
        payload["place_bearings"] = bearings
    heading = default_heading(map_data)
    if heading:
        payload["default_heading"] = heading
    if world_scale:
        payload["scale"] = "world"
        payload["density_percent"] = map_data.get("density_percent")
        payload["city_cell_max"] = 128
        payload["city_span_max"] = 9
        from app.world_scale import materials_for, people_leaning

        materials = map_data.get("materials")
        if not isinstance(materials, list) or not materials:
            materials = materials_for(str(map_data.get("preset_id") or ""))
        if materials:
            payload["materials"] = [str(item) for item in materials[:8]]
        leaning = people_leaning(map_data, px, py, terrain=str(here.get("state") or ""))
        if leaning:
            payload["people_leaning"] = leaning
    return payload
