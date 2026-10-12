"""Theme ability templates: the built-in library, the setup's theme mix, and the library that learns.

Built-in templates live in content/ability_templates/<theme>.json: per theme a label,
keywords for matching a custom setting, and abilities in the two-part growth shape
(name, description, cost, power_type, growth {pace, start, grows}, supernatural).

At generation the setup is scored against every theme's keywords (`theme_mix`); a
custom setting draws from its two or three best themes. `sample` hands the model a
few fresh templates per call, weighted toward the ones used least, so a template can
come back but rarely does. The model adapts a template (`template_id`) or invents a new
ability (`template_id: "new"`); `learn` verifies a new one (the ability quality gate on
engine growth, not a near-copy of anything in the library, not pool or fallback) and
stores it in the user library with the setup's themes. `record_chosen` counts the
abilities a game actually starts with, which raises their weight. The more is played,
the more the model has to draw from.

The user library sits next to the world database (data/ability_library.json) unless
AI_RPG_ABILITY_LIBRARY names a file, so anything that isolates AI_RPG_DB isolates it too.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUILTIN_DIR = ROOT / "content" / "ability_templates"
MAX_LEARNED = 1500
DEFAULT_THEME = "fantasy"
_LOCK = threading.Lock()
_builtin_cache: dict[str, Any] = {"stamp": None, "themes": {}, "entries": []}

# The setup's adapter hint (session_theme) points at a theme even without keywords.
_ADAPTER_THEMES = {"isekai_rpg": "isekai", "system_rpg": "apocalypse", "grimdark": "gothic", "mundane": "hearth"}

_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "your", "you", "one", "that", "it",
         "its", "at", "by", "from", "as", "is", "be", "can", "into", "per", "this", "when", "while", "their", "them",
         "until", "after", "they", "if", "any", "who", "what", "how", "for"}


def library_path() -> Path:
    explicit = os.getenv("AI_RPG_ABILITY_LIBRARY")
    if explicit:
        return Path(explicit)
    from app.db import db_path

    return Path(db_path()).parent / "ability_library.json"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:48]


def norm_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", str(name or "").lower().replace("'s", "")).strip()


def _words(text: Any) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", str(text or "").lower()) if w not in _STOP}


# --- loading --------------------------------------------------------------------

def _builtin_stamp() -> tuple:
    try:
        return tuple(sorted((p.name, p.stat().st_mtime) for p in BUILTIN_DIR.glob("*.json")))
    except OSError:
        return ()


def builtin() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """(themes, entries) from content/ability_templates, reloaded when a file changes."""
    stamp = _builtin_stamp()
    if _builtin_cache["stamp"] == stamp:
        return _builtin_cache["themes"], _builtin_cache["entries"]
    themes: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    for path in sorted(BUILTIN_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        theme = str(data.get("theme") or path.stem)
        themes[theme] = {"label": data.get("label") or theme, "keywords": [str(k).lower() for k in data.get("keywords") or []]}
        for ab in data.get("abilities") or []:
            if not isinstance(ab, dict) or not ab.get("name"):
                continue
            entries.append({**ab, "id": f"{theme}:{_slug(ab['name'])}", "themes": [theme], "source": "builtin"})
    _builtin_cache.update({"stamp": stamp, "themes": themes, "entries": entries})
    return themes, entries


def _empty_user() -> dict[str, Any]:
    return {"version": 1, "entries": [], "usage": {}}


def load_user() -> dict[str, Any]:
    path = library_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty_user()
    if not isinstance(data, dict):
        return _empty_user()
    data.setdefault("entries", [])
    data.setdefault("usage", {})
    return data


def _save_user(data: dict[str, Any]) -> None:
    path = library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def all_entries() -> list[dict[str, Any]]:
    _, entries = builtin()
    return list(entries) + [dict(e) for e in load_user().get("entries") or [] if isinstance(e, dict)]


# --- the setup's themes --------------------------------------------------------------

def _setup_text(setup: dict[str, Any]) -> str:
    setup = setup if isinstance(setup, dict) else {}
    intent = setup.get("_compose_intent") if isinstance(setup.get("_compose_intent"), dict) else {}
    theme = setup.get("session_theme") if isinstance(setup.get("session_theme"), dict) else {}
    parts = [
        setup.get("world_style"), setup.get("custom_style"), setup.get("world_style_custom"), setup.get("_randomize_idea"),
        setup.get("randomize_idea"), setup.get("tone"), setup.get("magic_level"),
        intent.get("genre"), intent.get("tone"), " ".join(str(k) for k in intent.get("keywords") or []),
        theme.get("genre"), theme.get("raw_idea"), " ".join(str(k) for k in theme.get("keywords") or []),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def theme_mix(setup: dict[str, Any] | None, *, top: int = 3) -> list[tuple[str, float]]:
    """The setup's themes, best first, with weights that sum to 1."""
    themes, _ = builtin()
    text = _setup_text(setup or {})
    scores: dict[str, float] = {}
    for theme, meta in themes.items():
        score = 0.0
        for kw in meta["keywords"]:
            if re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text):
                score += 1.0 + 0.3 * kw.count(" ")
        if score:
            scores[theme] = score
    st = (setup or {}).get("session_theme") if isinstance((setup or {}).get("session_theme"), dict) else {}
    intent = (setup or {}).get("_compose_intent") if isinstance((setup or {}).get("_compose_intent"), dict) else {}
    hinted = _ADAPTER_THEMES.get(str(st.get("adapter_hint") or intent.get("adapter_hint") or ""))
    if hinted in themes:
        scores[hinted] = scores.get(hinted, 0.0) + 1.0
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    if str(pf.get("growth") or "").lower() == "compounding" and "op_mc" in themes:
        scores["op_mc"] = scores.get("op_mc", 0.0) + 1.0
    if not scores:
        scores = {DEFAULT_THEME if DEFAULT_THEME in themes else next(iter(themes), DEFAULT_THEME): 1.0}
    best = sorted(scores.items(), key=lambda kv: -kv[1])[:top]
    total = sum(s for _, s in best) or 1.0
    return [(t, round(s / total, 3)) for t, s in best]


def _magic_off(setup: dict[str, Any] | None) -> bool:
    try:
        from app.setup_composer import magic_lane_stance

        s = setup or {}
        return magic_lane_stance(str(s.get("magic_level") or ""), s.get("race_magic_enabled")) == "off"
    except Exception:
        return False


# --- sampling -------------------------------------------------------------------

def sample(setup: dict[str, Any] | None, k: int = 8, *, exclude_names: list[str] | None = None,
           rng: random.Random | None = None) -> list[dict[str, Any]]:
    """A fresh handful of templates for this setup's theme mix; the least used are likelier."""
    rng = rng or random.Random()
    mix = dict(theme_mix(setup))
    usage = load_user().get("usage") or {}
    skip = {norm_name(n) for n in exclude_names or []}
    no_magic = _magic_off(setup)
    pool: list[tuple[float, dict[str, Any]]] = []
    for entry in all_entries():
        share = max((mix.get(t, 0.0) for t in entry.get("themes") or []), default=0.0)
        if share <= 0 or norm_name(entry.get("name")) in skip:
            continue
        if no_magic and entry.get("supernatural", True):
            continue
        used = usage.get(entry["id"]) or {}
        weight = share / (1.0 + float(used.get("used", 0)) + 0.25 * float(used.get("offered", 0)))
        weight *= 1.0 + 0.3 * min(5, float(used.get("chosen", 0)))
        if entry.get("source") == "learned":
            weight *= 1.15  # what this player's games produced comes up a little more often
        pool.append((weight, entry))
    picked: list[dict[str, Any]] = []
    while pool and len(picked) < k:
        total = sum(w for w, _ in pool)
        roll = rng.random() * total
        for i, (w, entry) in enumerate(pool):
            roll -= w
            if roll <= 0:
                picked.append(entry)
                pool.pop(i)
                break
        else:
            picked.append(pool.pop()[1])
    return picked


def prompt_view(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the model sees of each template (the growth seed in words, no numbers)."""
    return [
        {"template_id": t["id"], "name": t["name"], "description": t.get("description"), "cost": t.get("cost"),
         "power_type": t.get("power_type"), "growth": t.get("growth") or {}}
        for t in templates
    ]


def _bump(ids: list[str], field: str) -> None:
    ids = [i for i in ids if i]
    if not ids:
        return
    with _LOCK:
        data = load_user()
        usage = data.setdefault("usage", {})
        for i in ids:
            row = usage.setdefault(i, {})
            row[field] = int(row.get(field, 0)) + 1
            row["last"] = int(time.time())
        _save_user(data)


def record_offered(templates: list[dict[str, Any]]) -> None:
    _bump([t.get("id") for t in templates], "offered")


def record_used(template_ids: list[str]) -> None:
    _bump(list(template_ids), "used")


def record_chosen(abilities: list[dict[str, Any]]) -> list[str]:
    """A game started with these abilities: count each one that came from the library."""
    by_name = {norm_name(e["name"]): e["id"] for e in all_entries()}
    known = {e["id"] for e in all_entries()}
    ids = []
    for ab in abilities or []:
        if not isinstance(ab, dict):
            continue
        tid = str(ab.get("template_id") or "")
        if tid in known:
            ids.append(tid)
        elif norm_name(ab.get("name")) in by_name:
            ids.append(by_name[norm_name(ab.get("name"))])
    _bump(ids, "chosen")
    return ids


# --- learning ------------------------------------------------------------------

def _near_copy(ability: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    """The id of a library entry this ability copies, or ""."""
    name = norm_name(ability.get("name"))
    words = _words(ability.get("description"))
    for entry in entries:
        other = norm_name(entry.get("name"))
        if name and (name == other or difflib.SequenceMatcher(None, name, other, autojunk=False).ratio() >= 0.85):
            return entry["id"]
        ow = _words(entry.get("description"))
        if words and ow and len(words & ow) / len(words | ow) >= 0.5:
            return entry["id"]
    return ""


def verify(ability: dict[str, Any], entries: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
    """Whether a model-made ability may join the library, and why not."""
    if not isinstance(ability, dict) or not ability.get("name"):
        return False, "no_ability"
    if ability.get("_seed_pool") or ability.get("fallback"):
        return False, "pool_or_fallback"
    from app import ability_growth
    from app.llm import evaluate_ability_quality
    from app.setup_composer import is_overused_seed_domain

    card = ability_growth.build(ability)
    if is_overused_seed_domain(str(card.get("name") or "")):
        return False, "overused_domain"
    report = evaluate_ability_quality(card, require_strong_math=True, one_skillish=False)
    if not report.get("ok") or report.get("hard_fail"):
        return False, "quality:" + ",".join(report.get("hard_fail") or ["score"])
    copy_of = _near_copy(card, entries if entries is not None else all_entries())
    if copy_of:
        return False, f"copy_of:{copy_of}"
    return True, "ok"


def learn(abilities: list[dict[str, Any]], setup: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Store each new model-made ability that verifies. Returns the stored entries."""
    candidates = [a for a in abilities or [] if isinstance(a, dict)
                  and str(a.get("template_id") or "new") in {"", "new"}]
    if not candidates:
        return []
    themes = [t for t, _ in theme_mix(setup)]
    no_magic = _magic_off(setup)
    stored: list[dict[str, Any]] = []
    with _LOCK:
        data = load_user()
        entries = all_entries()
        for ab in candidates:
            ok, _why = verify(ab, entries)
            if not ok:
                continue
            growth = ab.get("growth") if isinstance(ab.get("growth"), dict) else {}
            entry = {
                "id": f"learned:{_slug(ab['name'])}:{hashlib.sha1(str(ab.get('description')).encode('utf-8')).hexdigest()[:6]}",
                "name": str(ab["name"])[:100],
                "description": str(ab.get("description") or "")[:800],
                "cost": str(ab.get("cost") or "")[:300],
                "power_type": str(ab.get("power_type") or growth.get("template") or "linear"),
                "growth": {k: growth.get(k) for k in ("pace", "start", "grows") if growth.get(k)},
                # A power from a no-magic world is mundane; otherwise assume it needs magic.
                "supernatural": not no_magic,
                "themes": themes,
                "source": "learned",
                "created": int(time.time()),
            }
            data["entries"].append(entry)
            entries.append(entry)
            stored.append(entry)
        if stored:
            if len(data["entries"]) > MAX_LEARNED:
                usage = data.get("usage") or {}
                data["entries"].sort(key=lambda e: (int((usage.get(e["id"]) or {}).get("chosen", 0)), e.get("created", 0)))
                data["entries"] = data["entries"][-MAX_LEARNED:]
            _save_user(data)
    return stored


def stats() -> dict[str, Any]:
    themes, entries = builtin()
    user = load_user()
    learned = user.get("entries") or []
    by_theme: dict[str, int] = {}
    for e in learned:
        for t in e.get("themes") or []:
            by_theme[t] = by_theme.get(t, 0) + 1
    return {"builtin": len(entries), "themes": len(themes), "learned": len(learned), "learned_by_theme": by_theme,
            "path": str(library_path())}
