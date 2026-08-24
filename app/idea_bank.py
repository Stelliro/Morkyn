"""
Cold-storage idea bank — keyword-searchable inspiration only.

Not a model, not embeddings, not weighted training data.
JSONL cards live on disk; setup/play prompts can pull a few sparks by keyword
match and inject them as "inspiration only" wording ideas.

Sources (merged, ship first then user overlays):
  config/idea_bank/*.jsonl   — shipped seeds
  data/idea_bank/*.jsonl     — local user/cold-storage adds (optional)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SHIPPED_DIR = ROOT / "config" / "idea_bank"
def user_dir() -> Path:
    """Resolved per call so AI_RPG_IDEA_BANK is honoured whatever the import order."""
    return Path(os.getenv("AI_RPG_IDEA_BANK", str(ROOT / "data" / "idea_bank")))

# kind → typical setup fields that benefit from that spark
KIND_FIELDS: dict[str, tuple[str, ...]] = {
    "ability": ("special_abilities", "custom_skills", "race_ability_rules"),
    "skill": ("custom_skills", "skill_style", "special_abilities", "proficiency_access"),
    "growth": ("special_abilities", "custom_skills", "skill_growth_speed", "xp_growth_speed"),
    "place": ("start_location", "world_style", "custom_style", "faction_pressure"),
    "tone": ("tone", "custom_style", "death_rules", "narration_detail"),
    "faction": ("faction_pressure", "quest_style", "npc_density", "custom_style"),
    "system": ("game_system", "system_style", "skill_style", "leveling_system"),
    "death": ("death_rules", "difficulty", "custom_style"),
    "loot": ("loot_rarity", "economy", "inventory_rules"),
    "npc": ("npc_stat_scaling", "npc_skill_frequency", "faction_pressure", "quest_style"),
    "style": ("world_style", "custom_style", "tone", "magic_level", "tech_level"),
    "opening": ("character_backstory", "start_location", "custom_style"),
}

_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "be",
    "as",
    "at",
    "by",
    "from",
    "that",
    "this",
    "it",
    "into",
    "only",
    "not",
    "no",
    "yes",
}

_cache: dict[str, Any] = {"mtime": 0.0, "cards": []}


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9][a-z0-9'_-]{1,40}", (text or "").lower())
    return [t for t in raw if t not in _STOP and len(t) > 1]


def _norm_card(raw: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or raw.get("name") or "").strip()
    text = str(raw.get("text") or raw.get("idea") or raw.get("blurb") or "").strip()
    if not title and not text:
        return None
    keywords = raw.get("keywords") or raw.get("tags") or []
    if isinstance(keywords, str):
        keywords = [p.strip() for p in re.split(r"[,;/|]", keywords) if p.strip()]
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [p.strip() for p in re.split(r"[,;/|]", tags) if p.strip()]
    examples = raw.get("examples") or []
    if isinstance(examples, str):
        examples = [examples]
    kind = str(raw.get("kind") or raw.get("category") or "style").strip().lower() or "style"
    card_id = str(raw.get("id") or "").strip()
    if not card_id:
        slug = re.sub(r"[^a-z0-9]+", "_", f"{kind}_{title}".lower()).strip("_")[:64]
        # blake2b, not hash(): card ids must be the same string in every process.
        card_id = slug or "idea_" + hashlib.blake2b(text.encode("utf-8", "replace"), digest_size=5).hexdigest()
    return {
        "id": card_id[:80],
        "kind": kind[:40],
        "title": (title or card_id)[:160],
        "text": text[:800],
        "keywords": [str(k).strip().lower()[:40] for k in keywords if str(k).strip()][:32],
        "tags": [str(t).strip().lower()[:40] for t in tags if str(t).strip()][:16],
        "examples": [str(e).strip()[:120] for e in examples if str(e).strip()][:8],
        "source": source[:200],
    }


def _iter_jsonl_paths() -> list[Path]:
    paths: list[Path] = []
    for folder in (SHIPPED_DIR, user_dir()):
        if not folder.is_dir():
            continue
        try:
            for path in sorted(folder.rglob("*.jsonl")):
                if path.is_file():
                    paths.append(path)
        except OSError:
            continue
    return paths


def _folder_mtime() -> float:
    latest = 0.0
    for path in _iter_jsonl_paths():
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def load_idea_cards(*, force: bool = False) -> list[dict[str, Any]]:
    """Load + cache all idea cards. Invalid lines are skipped."""
    mtime = _folder_mtime()
    if not force and _cache["cards"] and _cache["mtime"] == mtime:
        return list(_cache["cards"])
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in _iter_jsonl_paths():
        try:
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(path)
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    card = _norm_card(raw, source=rel)
                    if not card:
                        continue
                    # User overlays win on same id
                    if card["id"] in seen:
                        cards = [c for c in cards if c["id"] != card["id"]]
                    seen.add(card["id"])
                    cards.append(card)
        except OSError:
            continue
    _cache["cards"] = cards
    _cache["mtime"] = mtime
    return list(cards)


def idea_bank_stats() -> dict[str, Any]:
    cards = load_idea_cards()
    by_kind: dict[str, int] = {}
    for card in cards:
        by_kind[card["kind"]] = by_kind.get(card["kind"], 0) + 1
    return {
        "total": len(cards),
        "by_kind": dict(sorted(by_kind.items())),
        "shipped_dir": str(SHIPPED_DIR).replace("\\", "/"),
        "user_dir": str(user_dir()).replace("\\", "/"),
        "user_dir_exists": user_dir().is_dir(),
        "files": [
            (
                str(p.relative_to(ROOT)).replace("\\", "/")
                if str(p).startswith(str(ROOT))
                else str(p).replace("\\", "/")
            )
            for p in _iter_jsonl_paths()
        ],
    }


def _rank_and_sample(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """
    Pick `limit` matches, favouring score but not fixing the answer.

    Straight `sort(...)[:limit]` made the scored branch as repetitive as the
    no-query branch used to be: the same idea returned the same four cards on
    every roll, and a flat tie (a dozen cards all scoring 1.0) was broken by
    title, so the alphabetically-last twelve won forever.

    Relevance still gates the pool -- only cards scoring at least half the best
    score are eligible, so a weak 0.35 substring match can never displace a
    direct keyword hit. Inside that pool the choice is weighted by score, so a
    3.0 is drawn about three times as often as a 1.0 but neither is guaranteed.
    """
    take = max(1, min(int(limit or 8), 24))
    if len(results) <= take:
        return sorted(results, key=lambda r: r["score"], reverse=True)
    top = max(r["score"] for r in results)
    pool = [r for r in results if r["score"] >= top * 0.5] or results
    if len(pool) <= take:
        return sorted(pool, key=lambda r: r["score"], reverse=True)
    # Efraimidis-Spirakis: weighted sample without replacement.
    keyed = [(random.random() ** (1.0 / max(r["score"], 0.01)), r) for r in pool]
    keyed.sort(key=lambda pair: pair[0], reverse=True)
    picked = [r for _, r in keyed[:take]]
    picked.sort(key=lambda r: r["score"], reverse=True)
    return picked


def search_idea_bank(
    query: str,
    *,
    kind: str | None = None,
    kinds: list[str] | None = None,
    limit: int = 8,
    exclude_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Pure keyword search over cold storage.
    Score = keyword hits + title/text token hits. No learned weights.
    """
    cards = load_idea_cards()
    q_tokens = _tokens(query)
    if not q_tokens:
        # No query: a genuinely varied slice of the preferred kinds.
        #
        # This branch used to be guarded by "and not kind and not kinds", which
        # made its own kind-filtering unreachable, and it returned pool[:limit]
        # -- the first N cards in load order -- despite promising "random-ish".
        # A cold randomize therefore saw the same five cards out of 292 on every
        # call, and the setup it produced was the same world nine times in ten.
        pool = cards
        if kind:
            pool = [c for c in pool if c["kind"] == kind.lower()]
        if kinds:
            allow = {k.lower() for k in kinds}
            pool = [c for c in pool if c["kind"] in allow]
        exclude = {str(x) for x in (exclude_ids or []) if x}
        pool = [c for c in pool if c["id"] not in exclude]
        take = max(1, min(int(limit or 8), 12))
        if len(pool) <= take:
            return list(pool)
        return random.sample(pool, take)

    allow_kinds: set[str] | None = None
    if kind:
        allow_kinds = {kind.lower()}
    if kinds:
        allow_kinds = {*(allow_kinds or set()), *[k.lower() for k in kinds]}

    exclude = {str(x) for x in (exclude_ids or []) if x}
    results: list[dict[str, Any]] = []
    qset = set(q_tokens)
    for card in cards:
        if card["id"] in exclude:
            continue
        if allow_kinds and card["kind"] not in allow_kinds:
            continue
        hay_kw = set(card.get("keywords") or []) | set(card.get("tags") or [])
        hay_text = _tokens(f"{card.get('title') or ''} {card.get('text') or ''}")
        hay_text_set = set(hay_text)

        # Exact keyword / tag hits count more; body tokens less.
        kw_hits = len(qset & hay_kw)
        text_hits = len(qset & hay_text_set)
        if kw_hits == 0 and text_hits == 0:
            # substring soft match for short seeds (e.g. "wuxia")
            blob = " ".join(sorted(hay_kw | hay_text_set))
            soft = sum(1 for t in q_tokens if t in blob)
            if soft == 0:
                continue
            score = soft * 0.35
        else:
            score = kw_hits * 2.0 + text_hits * 1.0
            # slight boost when kind tokens appear in query
            if card["kind"] in qset:
                score += 0.5
        results.append({**card, "score": round(score, 3)})

    return _rank_and_sample(results, limit)


def kinds_for_field(field: str) -> list[str]:
    field = str(field or "").strip()
    out: list[str] = []
    for kind, fields in KIND_FIELDS.items():
        if field in fields:
            out.append(kind)
    return out or ["style", "tone"]


def _intent_defaults() -> dict[str, Any]:
    """The placeholder values `empty_intent()` hands out before the player types anything."""
    try:
        from app.setup_composer import DEFAULT_INTENT

        return DEFAULT_INTENT
    except Exception:  # pragma: no cover - setup_composer is always importable in app
        return {}


def _chosen(source: dict[str, Any] | None, key: str, *, group: str = "") -> str:
    """
    An intent value only when the player actually supplied it.

    A cold randomize compiles `empty_intent()`, whose unset slots hold sentinel
    strings rather than blanks: adapter_hint="default", start_power="ordinary",
    growth="steady". Feeding those to the search built the query
    "default ordinary steady" on EVERY cold roll, and those three words match
    exactly two cards in the whole bank -- so `style.low_fantasy_mud` and
    `ability.pulse_count` were pinned to the top of the sparks list forever.
    Measured live: 10/10 randomizations returned some spelling of "low fantasy
    mud and knives" as world_style.

    This is the same class of bug as the field-name leak below: prompt input
    that describes the FORM rather than the player's idea. Compared per key
    against that key's own default, so a genuine tone of "steady" still counts
    (tone defaults to ""); only a slot still holding its placeholder is dropped.
    """
    if not isinstance(source, dict):
        return ""
    value = source.get(key)
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    defaults = _intent_defaults()
    if group:
        defaults = defaults.get(group) if isinstance(defaults.get(group), dict) else {}
    default = defaults.get(key) if isinstance(defaults, dict) else None
    if isinstance(default, str) and text.lower() == default.strip().lower():
        return ""
    return text


def build_query_from_setup(
    current_setup: dict[str, Any] | None,
    *,
    fields: list[str] | None = None,
    intent: dict[str, Any] | None = None,
) -> str:
    """Assemble a short search string from idea + intent + nearby fields."""
    setup = current_setup or {}
    intent = intent if isinstance(intent, dict) else {}
    parts: list[str] = []
    idea = str(setup.get("_randomize_idea") or intent.get("raw_idea") or "").strip()
    if idea:
        parts.append(idea[:220])
    for key in ("genre", "tone", "adapter_hint", "edge"):
        val = _chosen(intent, key)
        if val:
            parts.append(val)
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    for key in ("start_power", "growth", "skill_summary"):
        val = _chosen(pf, key, group="power_fantasy")
        if val:
            parts.append(val)
    kws = intent.get("keywords") if isinstance(intent.get("keywords"), list) else []
    parts.extend(str(k) for k in kws[:8] if k)
    for f in fields or []:
        # The field NAME is deliberately not a search term. Relevance by field
        # is already handled by kinds_for_field(); adding "tone" or "world
        # style" as free text matches every card whose *kind* shares the word,
        # so a cold randomize searched for "world style tone custom style" and
        # got five tone cards, identically, on every call.
        val = setup.get(f)
        if isinstance(val, str) and val.strip():
            parts.append(val[:80])
        elif f == "special_abilities" and isinstance(val, list) and val:
            a0 = val[0] if isinstance(val[0], dict) else {}
            parts.append(str(a0.get("name") or "")[:40])
    for key in ("world_style", "tone", "custom_skills", "difficulty", "skill_style"):
        val = setup.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val[:60])
    return " ".join(parts)[:600]


def idea_sparks_for_prompt(
    current_setup: dict[str, Any] | None = None,
    *,
    fields: list[str] | None = None,
    intent: dict[str, Any] | None = None,
    limit: int = 5,
    query: str | None = None,
) -> dict[str, Any]:
    """
    Package for LLM prompts: cold-storage sparks with clear non-weighting rules.
    """
    setup = current_setup or {}
    intent = intent if isinstance(intent, dict) else {}
    field_list = [str(f) for f in (fields or []) if f]
    kinds: list[str] = []
    for f in field_list:
        kinds.extend(kinds_for_field(f))
    # unique preserve order
    seen_k: set[str] = set()
    kinds = [k for k in kinds if not (k in seen_k or seen_k.add(k))]  # type: ignore[func-returns-value]
    if not kinds:
        kinds = ["style", "tone", "ability", "place"]

    q = (query or build_query_from_setup(setup, fields=field_list, intent=intent)).strip()
    hits = search_idea_bank(q, kinds=kinds, limit=max(limit, 4))
    # If sparse, pad with same-kind random variety
    if len(hits) < limit:
        pad = search_idea_bank("", kinds=kinds, limit=limit + 4)
        have = {h["id"] for h in hits}
        for card in pad:
            if card["id"] in have:
                continue
            hits.append(card)
            if len(hits) >= limit:
                break

    sparks = []
    for card in hits[:limit]:
        sparks.append(
            {
                "id": card.get("id"),
                "kind": card.get("kind"),
                "title": card.get("title"),
                "text": card.get("text"),
                "keywords": card.get("keywords") or [],
                "examples": card.get("examples") or [],
            }
        )
    return {
        "mode": "cold_storage_keyword_search",
        "weighted": False,
        "trainable": False,
        "query": q[:300],
        "kinds": kinds,
        "sparks": sparks,
        "rules": [
            "These are IDEA SPARKS only — cold storage, not training weights.",
            "Borrow wording, domains, or concrete hooks. Write your own phrase; do not lift one whole.",
            "Prefer one fresh combination over pasting a whole spark.",
            "Ignore sparks that fight locked_setup or the player's idea.",
            "Never invent god-mode openings from a spark that is only flavor.",
        ],
    }


# What a spark carries into a prompt: the content, never the ready-made labels.
#
# `id` is an internal handle (`style.low_fantasy_mud`). `title` and `examples`
# are pre-written phrases sized exactly like a setup field value. All three were
# measured being pasted straight into the form:
#
#   world_style   = "low_fantasy_mud"                    (the id)
#   tone          = "pastoral_curious"                   (the id)
#   world_style   = "Low fantasy mud and knives"         (the title)
#   start_location= "a broken cart axle starts the plot" (the examples line)
#
# `text` and `keywords` say the same thing without handing over a finished
# answer -- "Magic is rumor; problems are hunger, weather, and people with
# knives" is richer than its own title, and the model has to write a phrase
# rather than copy one. Telling it not to copy did not work: the rule has said
# "Do not copy titles verbatim as final values" the whole time, and 13 verbatim
# titles still landed across 12 measured rolls.
_PROMPT_SPARK_FIELDS = ("kind", "text", "keywords")


def prompt_sparks(pkg: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    The prompt-safe view of a spark package.

    Callers that render sparks for a human (the search API, the setup UI) keep
    using the full package; only what is serialized into a prompt goes through
    here. Removing the fields is the whole fix -- the model cannot paste a
    string it was never shown.
    """
    if not isinstance(pkg, dict):
        return None
    sparks = pkg.get("sparks")
    if not isinstance(sparks, list):
        return dict(pkg)
    return {
        **pkg,
        "sparks": [
            {k: v for k, v in card.items() if k in _PROMPT_SPARK_FIELDS}
            if isinstance(card, dict)
            else card
            for card in sparks
        ],
    }


def append_user_idea(card: dict[str, Any], *, filename: str = "user_ideas.jsonl") -> dict[str, Any]:
    """Append one card to the user cold-storage folder."""
    normalized = _norm_card(card, source=f"data/idea_bank/{filename}")
    if not normalized:
        raise ValueError("Idea card needs title or text.")
    user_dir().mkdir(parents=True, exist_ok=True)
    path = user_dir() / filename
    # strip internal source before write; re-derive on load
    row = {
        "id": normalized["id"],
        "kind": normalized["kind"],
        "title": normalized["title"],
        "text": normalized["text"],
        "keywords": normalized["keywords"],
        "tags": normalized["tags"],
        "examples": normalized["examples"],
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    load_idea_cards(force=True)
    return row
