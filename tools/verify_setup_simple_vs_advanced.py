"""
Verify Simple vs Advanced setup Randomize against a live Morkyn + LLM.

Checks:
1) LLM is reachable and returns non-fallback values for key fields.
2) Advanced full walk fills advanced-depth fields (tone, quest_style, growth, etc.).
3) Simple visible-field walk only fills the Simple surface set (or thin defaults),
   then expand-depth pass fills advanced-depth fields before Start (as the UI does).
4) Field values land in the right keys (not slogan paste into difficulty, etc.).

Usage (server already running):
  set AI_RPG_BASE=http://127.0.0.1:8000
  python tools/verify_setup_simple_vs_advanced.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.getenv("AI_RPG_BASE", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = int(os.getenv("VERIFY_HTTP_TIMEOUT", "300"))
IDEA = os.getenv(
    "VERIFY_IDEA",
    "isekai, weak compounding skill seed, ordinary start, local stakes, fair DM, no harem",
).strip()[:400]

# Fields the Simple UI Confirm Randomize walks (must match SIMPLE_RANDOM_FIELD_ORDER in app.js)
SIMPLE_SURFACE = {
    "player_name",
    "player_age",
    "player_sex",
    "hair",
    "facial_features",
    "appearance",
    "backstory_mode",
    "memory_policy",
    "difficulty",
    "character_backstory",
    "world_style",
    "custom_style",
    "leveling_system",
    "game_system",
    "dice_checks_enabled",
    "proficiency_system",
    "skill_levels_enabled",
    "race_magic_enabled",
    "system_style",
    "magic_level",
    "death_rules",
    "starter_equipment",
    "special_abilities",
}

# Advanced-only-ish fields Simple expand is expected to fill at Start time
ADVANCED_DEPTH = {
    "tone",
    "tech_level",
    "economy",
    "start_location",
    "starter_equipment",
    "loot_rarity",
    "npc_density",
    "quest_style",
    "faction_pressure",
    "custom_skills",
    "narration_detail",
    "npc_stat_scaling",
    "rank_scale",
}

# Keys that must never receive idea slogans
ENUM_SAFE = {
    "difficulty": {"easy", "normal", "hard", "brutal"},
    "magic_level": {
        "none",
        "rare",
        "uncommon",
        "common",
        "everyday",
        "high",
        "pervasive",
        "ubiquitous",
    },
}


def http_json(method: str, path: str, body: dict | None = None, timeout: int = TIMEOUT) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail[:900]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} -> {exc}") from exc


def merge_fields(current: dict, payload: dict) -> dict:
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else None
    if fields:
        for k, v in fields.items():
            if v is None:
                continue
            current[k] = v
    else:
        for k, v in payload.items():
            if k.startswith("_") or k in {
                "notes",
                "locked_setup",
                "current_setup",
                "return_fields",
                "rules",
                "task",
                "quality_gate",
            }:
                continue
            if v is None:
                continue
            current[k] = v
    if "special_abilities" in payload and isinstance(payload["special_abilities"], list):
        current["special_abilities"] = payload["special_abilities"]
    if fields and isinstance(fields.get("special_abilities"), list):
        current["special_abilities"] = fields["special_abilities"]
    if payload.get("fallback_used") or payload.get("source") == "fallback":
        current.setdefault("_fallback_hits", 0)
        current["_fallback_hits"] = int(current.get("_fallback_hits") or 0) + 1
    if payload.get("quality_gate"):
        current.setdefault("_quality_gates", []).append(payload.get("quality_gate"))
    return current


def nonempty(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return True
    if isinstance(v, (list, dict)):
        return bool(v)
    return bool(str(v).strip())


def is_defaultish(name: str, v) -> bool:
    s = str(v or "").strip().lower()
    defaults = {
        "start_location": {"", "mosswake gate"},
        "world_style": {"", "frontier dark fantasy"},
        "tone": {"", "grounded adventure"},
        "difficulty": {"", "normal"},
        "tech_level": {"", "iron age"},
        "magic_level": {"", "rare"},
        "economy": {"", "scarce"},
        "quest_style": {"", "emergent"},
        "faction_pressure": {"", "local disputes"},
        "player_name": {"", "wanderer"},
    }
    return s in defaults.get(name, {""})


def randomize_field(current: dict, field: str, *, idea: str, intent: dict | None) -> dict:
    body_current = dict(current)
    body_current["_randomize_idea"] = idea
    if intent:
        body_current["_compose_intent"] = intent
    locked = list(current.get("_locked_fields") or [])
    body_current["_locked_fields"] = locked
    t0 = time.perf_counter()
    payload = http_json(
        "POST",
        "/api/randomize-setup",
        {"group": f"field:{field}", "current": body_current},
    )
    dt = time.perf_counter() - t0
    merge_fields(current, payload)
    current.setdefault("_timings", {})[field] = round(dt, 2)
    current.setdefault("_sources", {})[field] = (
        "fallback"
        if payload.get("fallback_used") or payload.get("source") in {"fallback", "local"}
        else "llm"
    )
    # quality gate / notes
    if payload.get("notes"):
        current.setdefault("_notes", {})[field] = str(payload.get("notes"))[:200]
    if isinstance(payload.get("quality_gate"), dict):
        current.setdefault("_quality_gates", []).append(
            {"field": field, **{k: payload["quality_gate"].get(k) for k in ("ok", "source", "score")}}
        )
    return payload


def walk_fields(fields: list[str], *, idea: str, intent: dict | None, label: str) -> dict:
    current: dict = {
        "_locked_fields": [],
        "_randomize_idea": idea,
    }
    if intent:
        current["_compose_intent"] = intent
    print(f"\n=== {label}: walking {len(fields)} fields ===", flush=True)
    for i, field in enumerate(fields, 1):
        print(f"  [{i}/{len(fields)}] {field} ...", end=" ", flush=True)
        try:
            randomize_field(current, field, idea=idea, intent=intent)
            src = current.get("_sources", {}).get(field, "?")
            val = current.get(field)
            preview = str(val)[:70].replace("\n", " ") if not isinstance(val, list) else f"[{len(val)} abilities]"
            print(f"{src} · {preview}", flush=True)
        except Exception as exc:
            print(f"ERR {exc}", flush=True)
            current.setdefault("_errors", {})[field] = str(exc)[:300]
    return current


def walk_groups(groups: list[str], *, idea: str, intent: dict | None, label: str) -> dict:
    """Faster Advanced-style walk: UI groups (character/world/people/rules/checks)."""
    current: dict = {
        "_locked_fields": [],
        "_randomize_idea": idea,
    }
    if intent:
        current["_compose_intent"] = intent
    print(f"\n=== {label}: groups {groups} ===", flush=True)
    for i, group in enumerate(groups, 1):
        print(f"  [{i}/{len(groups)}] group:{group} ...", end=" ", flush=True)
        body_current = dict(current)
        body_current["_randomize_idea"] = idea
        if intent:
            body_current["_compose_intent"] = intent
        t0 = time.perf_counter()
        try:
            payload = http_json(
                "POST",
                "/api/randomize-setup",
                {"group": group, "current": body_current},
            )
            merge_fields(current, payload)
            dt = time.perf_counter() - t0
            current.setdefault("_timings", {})[f"group:{group}"] = round(dt, 2)
            keys = []
            fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
            if isinstance(fields, dict):
                keys = [k for k in fields if not str(k).startswith("_") and k not in {"notes", "task", "rules"}]
            # mark sources
            for k in keys:
                current.setdefault("_sources", {})[k] = (
                    "fallback"
                    if payload.get("fallback_used") or payload.get("source") in {"fallback", "local"}
                    else "llm"
                )
            print(f"ok {dt:.1f}s keys={keys[:12]}{'…' if len(keys) > 12 else ''}", flush=True)
        except Exception as exc:
            print(f"ERR {exc}", flush=True)
            current.setdefault("_errors", {})[f"group:{group}"] = str(exc)[:300]
    return current


def main() -> int:
    print(f"BASE={BASE}", flush=True)
    print(f"IDEA={IDEA}", flush=True)

    # Health / model
    try:
        health = http_json("GET", "/api/model-config", timeout=30)
    except Exception as exc:
        print(f"FAIL: cannot reach Morkyn at {BASE}: {exc}")
        return 2
    provider = health.get("provider") or health.get("llm_provider") or "?"
    model = health.get("ollama_model") or health.get("api_model") or health.get("model") or "?"
    print(f"model-config provider={provider} model={model}", flush=True)

    try:
        ready = http_json("POST", "/api/model-ready", {}, timeout=60)
        print(f"model-ready: {json.dumps(ready)[:300]}", flush=True)
    except Exception as exc:
        print(f"model-ready skipped/failed: {exc}", flush=True)

    # Composer order
    composer = http_json("GET", "/api/setup/composer", timeout=30)
    field_order = list(composer.get("field_order") or [])
    if not field_order:
        print("FAIL: empty field_order from /api/setup/composer")
        return 2
    print(f"composer fields: {len(field_order)}", flush=True)

    # Intent
    composed = http_json(
        "POST",
        "/api/setup/compose-intent",
        {"idea": IDEA, "current": {"_locked_fields": []}},
        timeout=120,
    )
    intent = composed.get("intent") if isinstance(composed.get("intent"), dict) else {}
    session_theme = composed.get("session_theme") if isinstance(composed.get("session_theme"), dict) else {}
    overrides = composed.get("field_overrides") if isinstance(composed.get("field_overrides"), dict) else {}
    print(
        f"compose source={composed.get('source')} isekai={intent.get('isekai')} "
        f"genre={intent.get('genre')!r} overrides={list(overrides)[:8]}",
        flush=True,
    )

    mode = os.getenv("VERIFY_MODE", "mixed").strip().lower()
    # mixed (default): Advanced via groups (fast, matches group buttons) +
    # Simple via surface fields + expand (matches Start path).
    # full: every field (slow on 8B).
    if mode == "full":
        advanced = walk_fields(field_order, idea=IDEA, intent=intent, label="ADVANCED full field walk")
    else:
        advanced = walk_groups(
            ["world", "people", "rules", "character", "checks"],
            idea=IDEA,
            intent=intent,
            label="ADVANCED group walk",
        )
        # Powers are often their own group path
        if "special_abilities" not in advanced or not advanced.get("special_abilities"):
            print("  field:special_abilities ...", end=" ", flush=True)
            try:
                randomize_field(advanced, "special_abilities", idea=IDEA, intent=intent)
                print(str(advanced.get("special_abilities"))[:80], flush=True)
            except Exception as exc:
                print(f"ERR {exc}", flush=True)
    for k, v in overrides.items():
        if k not in advanced or is_defaultish(k, advanced.get(k)):
            advanced[k] = v

    # ---- Simple surface: only fields Simple UI cares about ----
    # UI Simple Confirm currently runs full randomize then pullFormToSimple, but
    # Start expands depth. We test the intended product contract:
    # Simple roll → surface fields; expand → advanced depth (Start path).
    simple_surface_fields = [f for f in field_order if f in SIMPLE_SURFACE]
    simple = walk_fields(simple_surface_fields, idea=IDEA, intent=intent, label="SIMPLE surface walk")
    for k, v in overrides.items():
        if k in SIMPLE_SURFACE:
            simple[k] = v

    # Snapshot: advanced-only fields should be empty/default on simple surface
    simple_before_expand = {
        k: simple.get(k) for k in ADVANCED_DEPTH if nonempty(simple.get(k)) and not is_defaultish(k, simple.get(k))
    }

    # ---- Simple expand (Start path: expandSimpleSetupDepth) ----
    expand_targets = [
        "world_style",
        "tone",
        "tech_level",
        "magic_level",
        "economy",
        "custom_style",
        "world_races",
        "start_location",
        "hair",
        "facial_features",
        "starter_equipment",
        "character_backstory",
        "death_rules",
        "loot_rarity",
        "npc_density",
        "quest_style",
        "faction_pressure",
        "custom_skills",
        "special_abilities",
    ]
    print("\n=== SIMPLE expand (Start-time advanced depth) ===", flush=True)
    for field in expand_targets:
        # Skip if already substantial (mirror UI thresholds loosely)
        if field == "special_abilities" and simple.get("special_abilities"):
            print(f"  skip {field} (already has abilities)", flush=True)
            continue
        if field == "character_backstory" and len(str(simple.get("character_backstory") or "")) >= 180:
            print(f"  skip {field} (long enough)", flush=True)
            continue
        if field == "start_location" and not is_defaultish("start_location", simple.get("start_location")):
            print(f"  skip {field} (already set)", flush=True)
            continue
        if field in simple and nonempty(simple.get(field)) and not is_defaultish(field, simple.get(field)):
            if field not in {"world_style", "magic_level", "death_rules", "hair", "facial_features"}:
                # still allow refresh of thin values
                if len(str(simple.get(field) or "")) >= 20 and field != "special_abilities":
                    print(f"  skip {field} (filled)", flush=True)
                    continue
        print(f"  expand {field} ...", end=" ", flush=True)
        try:
            randomize_field(simple, field, idea=IDEA, intent=intent)
            print(current_preview := str(simple.get(field))[:60].replace("\n", " "), flush=True)
        except Exception as exc:
            print(f"ERR {exc}", flush=True)

    # ---- Assertions / report ----
    findings: list[dict] = []

    def fail(code: str, detail: str) -> None:
        findings.append({"sev": "fail", "code": code, "detail": detail})
        print(f"FAIL [{code}] {detail}", flush=True)

    def warn(code: str, detail: str) -> None:
        findings.append({"sev": "warn", "code": code, "detail": detail})
        print(f"WARN [{code}] {detail}", flush=True)

    def ok(code: str, detail: str) -> None:
        findings.append({"sev": "ok", "code": code, "detail": detail})
        print(f"OK   [{code}] {detail}", flush=True)

    # LLM actually ran
    adv_llm = sum(1 for f, s in (advanced.get("_sources") or {}).items() if s == "llm")
    sim_llm = sum(1 for f, s in (simple.get("_sources") or {}).items() if s == "llm")
    adv_total = max(1, len([k for k in advanced if not str(k).startswith("_")]))
    if adv_llm < 3 and not any(k.startswith("group:") for k in (advanced.get("_timings") or {})):
        fail("advanced_llm_sparse", f"only {adv_llm} fields marked llm")
    else:
        ok("advanced_llm", f"{adv_llm} field sources llm (or group walk); filled keys≈{adv_total}")
    if sim_llm < 3:
        fail("simple_llm_sparse", f"only {sim_llm} simple surface fields from LLM")
    else:
        ok("simple_llm", f"{sim_llm} simple surface fields from LLM path")

    # Advanced filled advanced depth
    adv_filled = [k for k in ADVANCED_DEPTH if nonempty(advanced.get(k)) and not is_defaultish(k, advanced.get(k))]
    if len(adv_filled) < len(ADVANCED_DEPTH) * 0.6:
        fail("advanced_depth_thin", f"filled {adv_filled}")
    else:
        ok("advanced_depth", f"filled {len(adv_filled)}/{len(ADVANCED_DEPTH)} advanced-depth fields")

    # Simple surface walk should NOT have filled most advanced-depth fields
    leaked = list(simple_before_expand.keys())
    # world_style/magic may appear if in SIMPLE_SURFACE — exclude those
    leaked = [k for k in leaked if k not in SIMPLE_SURFACE]
    if leaked:
        # Soft: surface walk might still touch some if we wrongly included them
        warn("simple_surface_leaked_advanced", f"before expand already had {leaked}")
    else:
        ok("simple_surface_scoped", "advanced-depth empty/default before expand")

    # After expand, advanced depth should be present
    exp_filled = [k for k in ADVANCED_DEPTH if nonempty(simple.get(k)) and not is_defaultish(k, simple.get(k))]
    if len(exp_filled) < len(ADVANCED_DEPTH) * 0.5:
        fail("simple_expand_thin", f"after expand filled {exp_filled}")
    else:
        ok("simple_expand", f"after expand filled {len(exp_filled)}/{len(ADVANCED_DEPTH)} advanced-depth fields")

    # Enum fields not slogan-pasted
    for setup_name, bag in (("advanced", advanced), ("simple", simple)):
        for key, allowed in ENUM_SAFE.items():
            val = str(bag.get(key) or "").strip().lower()
            if not val:
                continue
            # allow aliases like "rare magic" containing rare
            if val not in allowed and not any(a in val for a in allowed):
                fail("enum_slogan", f"{setup_name}.{key}={val!r} not in {sorted(allowed)[:6]}…")
            else:
                ok("enum_ok", f"{setup_name}.{key}={val!r}")

    # Correct field content types
    bs = str(simple.get("character_backstory") or "")
    if len(bs) < 80:
        fail("backstory_short", f"len={len(bs)}")
    else:
        ok("backstory_len", f"len={len(bs)}")
        # should not be pure skill meta
        if "growth math" in bs.lower() or "weak seed skill:" in bs.lower():
            fail("backstory_skill_meta", bs[:120])

    name = str(advanced.get("player_name") or simple.get("player_name") or "")
    if name and name.lower() in {"wanderer", "player", "hero", "ash", "river"}:
        warn("name_generic", name)
    elif name:
        ok("name_set", name)

    loc = str(simple.get("start_location") or advanced.get("start_location") or "")
    if loc:
        ok("start_location", loc)

    abs_list = advanced.get("special_abilities") or simple.get("special_abilities") or []
    if isinstance(abs_list, list) and abs_list:
        a0 = abs_list[0] if isinstance(abs_list[0], dict) else {}
        an = str(a0.get("name") or "")
        if re_num := __import__("re").search(r"\s+\d{1,3}$", an):
            fail("ability_numeric_suffix", an)
        else:
            ok("ability_name", an)
        if not str(a0.get("description") or "").strip():
            fail("ability_empty_desc", an)
        else:
            ok("ability_desc", f"{an}: {str(a0.get('description'))[:50]}")

    # Report file
    out_dir = ROOT / "data" / "playtest_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = {
        "stamp": stamp,
        "base": BASE,
        "idea": IDEA,
        "provider": provider,
        "model": model,
        "intent": intent,
        "session_theme": session_theme,
        "overrides": overrides,
        "advanced_keys": sorted(k for k in advanced if not k.startswith("_")),
        "simple_keys": sorted(k for k in simple if not k.startswith("_")),
        "advanced_sample": {
            k: advanced.get(k)
            for k in (
                "world_style",
                "tone",
                "difficulty",
                "start_location",
                "player_name",
                "character_backstory",
                "special_abilities",
                "quest_style",
                "custom_skills",
            )
        },
        "simple_sample": {
            k: simple.get(k)
            for k in (
                "world_style",
                "difficulty",
                "player_name",
                "character_backstory",
                "start_location",
                "special_abilities",
                "tone",
                "quest_style",
                "starter_equipment",
            )
        },
        "simple_before_expand_advanced_hits": simple_before_expand,
        "timings_advanced": advanced.get("_timings"),
        "timings_simple": simple.get("_timings"),
        "sources_advanced": advanced.get("_sources"),
        "sources_simple": simple.get("_sources"),
        "quality_gates": (advanced.get("_quality_gates") or []) + (simple.get("_quality_gates") or []),
        "findings": findings,
        "summary": {
            "fails": sum(1 for f in findings if f["sev"] == "fail"),
            "warns": sum(1 for f in findings if f["sev"] == "warn"),
            "oks": sum(1 for f in findings if f["sev"] == "ok"),
        },
    }
    path = out_dir / f"verify-simple-advanced-{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    print(f"\nWrote {path}", flush=True)
    print(json.dumps(report["summary"], indent=2), flush=True)

    return 1 if report["summary"]["fails"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
