"""Per-turn digest of a harness run: python analyze.py <run dir> [first] [last]."""
import json, re, sys, statistics
from pathlib import Path
run = Path(sys.argv[1]); first = int(sys.argv[2]) if len(sys.argv) > 2 else 1; last = int(sys.argv[3]) if len(sys.argv) > 3 else 999
KEEP = {"gold", "inventory", "movement", "place", "npc", "quest", "check", "attack", "unnamed", "agency", "prose"}
SKIP_DEC = {"gold_shadow", "turn_start_kept", "placeholder_op_dropped", "where_ended_asked"}
COIN = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty)\s+(copper|coppers|silver|silvers|gold|coins?|pieces)\b", re.I)
secs, calls = [], []
for p in sorted(run.glob("turns/[0-9][0-9][0-9].json")):
    n = int(p.stem)
    if n < first or n > last or n == 0: continue
    r = json.load(open(p)); b, a = r["before"], r["after"]
    secs.append(r["seconds"]); calls.append(len(r.get("model_calls") or []))
    gd = (a["player"].get("gold") or 0) - (b["player"].get("gold") or 0)
    hd = (a["player"].get("health") or 0) - (b["player"].get("health") or 0)
    inv_b, inv_a = set(b["inventory"]), set(a["inventory"])
    clock = ((r["engine"].get("delta") or {}).get("clock") or {})
    mins = int(clock.get("to", {}).get("world_minute", 0) or 0) - int(clock.get("from", {}).get("world_minute", 0) or 0)
    rows = (r["engine"].get("delta") or {}).get("new_rows")
    print(f"\n## T{n} ({r['seconds']}s, {len(r.get('model_calls') or [])} calls{', FALLBACK ' + r['fallback_reason'] if r['used_fallback'] else ''})")
    print(f"  > {r['player_line']}")
    loc = b["location"] if b["location"] == a["location"] else f"{b['location']} -> {a['location']}"
    print(f"  at {loc} | gold {b['player'].get('gold')}{'' if not gd else f' -> {a['player'].get('gold')}'} | hp {a['player'].get('health')}{'' if not hd else f' ({hd:+})'} | energy {a['player'].get('energy')} | +{mins} min")
    if inv_a - inv_b: print("  inv +", sorted(inv_a - inv_b))
    if inv_b - inv_a: print("  inv -", sorted(inv_b - inv_a))
    if rows: print("  new rows:", json.dumps(rows)[:300])
    coins = COIN.findall(r["narration"])
    if coins: print("  coins in prose:", [" ".join(c) for c in coins][:8])
    for d in r["dice"]:
        if d["kind"] in ("damage", "gold") and d["value"]: print(f"  die {d['tag']} {d['notation']}={d['value']} ({d['source']})")
        if d["kind"] not in ("xp", "damage", "karma", "gold"): print(f"  die {d['tag']} {d['kind']} {d['band']} {d['notation']}={d['value']}")
    for note in r["engine"]["notes"]:
        if note.get("area") in KEEP and note.get("decision") not in SKIP_DEC:
            print("  ·", json.dumps({k: v for k, v in note.items() if k not in ("at", "asks", "unconfirmed", "seconds", "error", "area")})[:220])
    tail = re.sub(r"\s+", " ", r["narration"])[-260:]
    print("  prose end:", tail)
if secs:
    print(f"\n{len(secs)} turns: median {statistics.median(secs):.1f}s mean {statistics.mean(secs):.1f}s max {max(secs):.1f}s; model calls median {statistics.median(calls)}")
