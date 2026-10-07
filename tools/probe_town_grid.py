"""
Probe the town grid generator (docs/TownGrid.md, slice A) on an isolated world.

Builds a world in a temp directory (never under data/), then generates:
  * the centre (128) cell of the largest city, an outer cell of it, and a hamlet;
  * every cell of the largest city, one at a time, as a stress run.
Prints generation time and peak memory per cell and for the whole largest city,
stored row sizes, load/decode time, skeleton and city_ports time, plot and shop
counts per district type (after caps), unplaced stalls, and an ASCII window of
the centre cell to read by eye.

    .venv\\Scripts\\python.exe tools\\probe_town_grid.py [--seed N] [--density P] [--preset ID] [--no-city]
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-town-probe-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import town_grid as tg  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.tile_world import generate_scaled_world, get_map  # noqa: E402


def _row_bytes(conn, map_id: str, cx: int, cy: int) -> int:
    row = conn.execute(
        "SELECT length(roads) + length(segments) + length(streets) + length(plots) AS n FROM town_cells "
        "WHERE map_id = ? AND cx = ? AND cy = ?",
        (map_id, cx, cy),
    ).fetchone()
    return int(row["n"] or 0) if row else 0


def _timed_generate(conn, chart, city, cell) -> tuple[float, int, dict]:
    """Wall time of get_cell(create) (generate, encode, store), then the peak
    memory of one pure generation of the same cell, measured separately because
    tracemalloc slows Python several times over."""
    start = time.perf_counter()
    town = tg.get_cell(conn, chart, int(cell["x"]), int(cell["y"]), create=True)
    elapsed = (time.perf_counter() - start) * 1000
    tracemalloc.start()
    tg.generate_cell(chart, city, cell, town["era"])
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, peak, town


def _shares(towns: list[dict], cells_by_xy: dict) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for town in towns:
        cell = cells_by_xy[(town["cx"], town["cy"])]
        districts = cell.get("districts") or []
        for plot in town["plots"]:
            if plot.get("f") is None or plot.get("k") in ("gate", "temple", "office", "barracks") and "anchor" in (plot.get("fl") or []):
                continue
            d = int(plot.get("d", -1))
            kind = str((districts[d] if 0 <= d < len(districts) else {}).get("type") or "?")
            row = out.setdefault(kind, {"frontage": 0, "shop": 0, "service": 0})
            row["frontage"] += 1
            if plot.get("k") in ("shop", "service"):
                row[plot["k"]] += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261007)
    parser.add_argument("--density", type=int, default=60)
    parser.add_argument("--preset", default="forest_march")
    parser.add_argument("--no-city", action="store_true", help="skip generating the whole largest city")
    args = parser.parse_args()

    init_db()
    started = time.perf_counter()
    generate_scaled_world(preset_id=args.preset, seed=args.seed, density_percent=args.density, notice_percent=40)
    print(f"world built in {(time.perf_counter() - started):.1f} s (data dir {_TMP})")
    chart = get_map(None)
    cities = [c for c in chart["cities"] if isinstance(c, dict)]
    largest = max(cities, key=lambda c: (int(c.get("footprint") or 0), int(c.get("population") or 0)))
    smallest = min(cities, key=lambda c: (int(c.get("footprint") or 0), max(int(x["side"]) for x in c["cells"])))
    print(f"cities {len(cities)}; largest {largest['id']} {largest['name']} footprint {largest['footprint']} "
          f"span {largest['span']} band {largest['band']}; smallest {smallest['id']} footprint {smallest['footprint']} "
          f"side {max(int(x['side']) for x in smallest['cells'])}")

    start = time.perf_counter()
    ports = tg.city_ports(chart, largest)
    print(f"city_ports(largest): {(time.perf_counter() - start) * 1000:.2f} ms cold, "
          f"{sum(len(v) for v in ports.values())} ports, gates {[p['label'] for v in ports.values() for p in v if p.get('gate')]}")

    centre = max(largest["cells"], key=lambda c: int(c["side"]))
    outer = min(largest["cells"], key=lambda c: int(c["side"]))
    hamlet = max(smallest["cells"], key=lambda c: int(c["side"]))

    tg.clear_caches()
    start = time.perf_counter()
    tg.skeleton(chart, largest, centre)
    print(f"skeleton(centre {centre['side']}): {(time.perf_counter() - start) * 1000:.1f} ms")

    cells_by_xy = {(int(c["x"]), int(c["y"])): c for city in cities for c in city["cells"]}
    with connect() as conn:
        map_id = str(chart["id"])
        # Warm the imports (app.world, venues, local_intel, pools) so the first
        # timed cell measures generation, not module loading.
        warm = time.perf_counter()
        ctx = tg._world_name_context(conn)
        tg.generate_cell(chart, smallest, hamlet, str(ctx.get("era") or ""))
        print(f"warm-up (imports + one hamlet in memory): {(time.perf_counter() - warm) * 1000:.0f} ms")
        sample = []
        for label, city, cell in (("centre", largest, centre), ("outer", largest, outer), ("hamlet", smallest, hamlet)):
            elapsed, peak, town = _timed_generate(conn, chart, city, cell)
            sample.append(town)
            kinds: dict[str, int] = {}
            for plot in town["plots"]:
                kinds[plot["k"]] = kinds.get(plot["k"], 0) + 1
            print(f"{label:7s} side {town['side']:3d}: {elapsed:7.1f} ms, peak {peak / 1024:7.0f} KiB, "
                  f"row {_row_bytes(conn, map_id, town['cx'], town['cy']) / 1024:5.1f} KiB, plots {len(town['plots'])}, "
                  f"segments {len(town['segments'])}, streets {len(town['streets'])}, kinds {dict(sorted(kinds.items()))}")
        conn.commit()

        tg.clear_caches()
        start = time.perf_counter()
        tg.stored_cell(conn, chart, int(centre["x"]), int(centre["y"]))
        print(f"load+decode centre row (cold): {(time.perf_counter() - start) * 1000:.1f} ms")

        print("\ncentre cell, 64 x 40 window around the middle:")
        side = int(sample[0]["side"])
        print(tg.ascii_render(sample[0], x0=max(0, side // 2 - 32), y0=max(0, side // 2 - 20), width=64, height=40))
        print("legend: # avenue  = main  - street  : alley  $ shop  & service  h house  . yard  w warehouse  "
              "_ empty  T temple  O office  B barracks  G gate")
        names = [p["name"] for p in sample[0]["plots"] if p.get("name")]
        print("\nsome names:", names[:16])
        print("some streets:", sample[0]["streets"][:12])

        if not args.no_city:
            times = []
            towns = []
            city_start = time.perf_counter()
            for cell in sorted(largest["cells"], key=lambda c: (c["y"], c["x"])):
                one = time.perf_counter()
                town = tg.get_cell(conn, chart, int(cell["x"]), int(cell["y"]), create=True)
                times.append((time.perf_counter() - one) * 1000)
                towns.append(town)
            city_ms = (time.perf_counter() - city_start) * 1000
            conn.commit()
            total_bytes = sum(_row_bytes(conn, map_id, t["cx"], t["cy"]) for t in towns)
            # Memory held while the whole city is loaded through the cache (LRU of 9 decoded cells).
            tg.clear_caches()
            tracemalloc.start()
            for cell in largest["cells"]:
                tg.stored_cell(conn, chart, int(cell["x"]), int(cell["y"]))
            held, load_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            print(f"\nwhole largest city ({len(towns)} cells, 3 already stored): {city_ms / 1000:.2f} s, per cell median "
                  f"{statistics.median(times):.0f} ms, max {max(times):.0f} ms; stored {total_bytes / 1024:.0f} KiB; "
                  f"plots {sum(len(t['plots']) for t in towns)}; loading every row through the LRU holds "
                  f"{held / 1024 / 1024:.1f} MiB (peak {load_peak / 1024 / 1024:.1f} MiB)")
            report_towns = towns
        else:
            report_towns = sample
        print("\nshop share per district type (after caps; frontage plots, landmarks and gates excluded):")
        for kind, row in sorted(_shares(report_towns, cells_by_xy).items()):
            share = (row["shop"] + row["service"]) / max(1, row["frontage"])
            print(f"  {kind:13s} frontage {row['frontage']:6d}  shop {row['shop']:5d}  service {row['service']:5d}  share {share:5.2f}")
        from app.local_intel import stalls_for_district

        placed = 0
        expected = 0
        for town in report_towns:
            placed += sum(1 for p in town["plots"] if p.get("st"))
            cell = cells_by_xy[(town["cx"], town["cy"])]
            for district in cell.get("districts") or []:
                stalls = stalls_for_district(cell, district, theme=str(chart.get("theme") or ""),
                                             slavery=bool(chart.get("allows_slavery")))
                expected += sum(1 for s in stalls if not s.get("filler"))
        print(f"stalls (non-filler) {expected}, placed on plots {placed}, unplaced {expected - placed}")

    if not args.no_city:
        _synthetic_full_city(args.seed)


def _synthetic_full_city(seed: int) -> None:
    """The largest shape the world builder allows (a 9 x 9 box), generated whole in memory.

    The game never does this (generation is per cell, on demand); it bounds
    the worst case a campaign could reach by walking every cell of the
    biggest city.
    """
    import random

    from app.world_scale import build_city

    city = build_city(random.Random(seed), origin=(4000, 4000), box_w=9, box_h=9, single_side=None,
                      slavery=False, city_id="C1", name="Probe")
    city["band"] = "metropolis"
    world = {"id": "probe-9x9", "seed": seed, "theme": "medieval", "cities": [city], "roads": [], "scale": "world"}
    times = []
    peak_max = 0
    sizes = []
    plots = 0
    total_start = time.perf_counter()
    for cell in sorted(city["cells"], key=lambda c: (c["y"], c["x"])):
        one = time.perf_counter()
        town = tg.generate_cell(world, city, cell, "preindustrial")
        times.append((time.perf_counter() - one) * 1000)
        enc = tg.encode_cell(town)
        sizes.append(sum(len(v) for v in enc.values() if isinstance(v, str)))
        plots += len(town["plots"])
    total = time.perf_counter() - total_start
    biggest = max(city["cells"], key=lambda c: int(c["side"]))
    tracemalloc.start()
    tg.generate_cell(world, city, biggest, "preindustrial")
    _cur, peak_max = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\nsynthetic 9 x 9 box city ({len(city['cells'])} cells, sides {min(int(c['side']) for c in city['cells'])}-"
          f"{int(biggest['side'])}): {total:.2f} s in memory, per cell median {statistics.median(times):.0f} ms, "
          f"max {max(times):.0f} ms; encoded {sum(sizes) / 1024:.0f} KiB total, max row {max(sizes) / 1024:.1f} KiB; "
          f"plots {plots}; peak memory of the 128 cell {peak_max / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    main()
