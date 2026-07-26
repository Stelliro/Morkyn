"""
Board-wide setup cross-checks: duplicates, spam patterns, and cross-field inconsistencies.

Runs after field sanitize + consistency lint + starter gear logic.
Repairs what can be fixed deterministically; records findings for quality gates / UI.
"""
from __future__ import annotations

import re
from typing import Any

# --- tokens / patterns -------------------------------------------------------

_STOP = frozenset(
    """
    a an the and or of to in on for with from by as at is are was were be been
    into onto over under when while that this those these their they them you
    your your your not no nor only just more most very
    """.split()
)

_SLOGAN_MARKERS = (
    "compounding",
    "near-useless",
    "near useless",
    "op mc",
    "power fantasy",
    "player agency",
    "never auto-win",
    "growth math",
    "fair dm",
    "chosen one",
    "destined hero",
    "level 99",
    "all skills unlocked",
)

_STRUCTURE_FIELDS = frozenset(
    {
        "world_style",
        "tone",
        "difficulty",
        "economy",
        "quest_style",
        "faction_pressure",
        "npc_density",
        "npc_stat_scaling",
        "npc_skill_frequency",
        "death_rules",
        "loot_rarity",
        "tech_level",
        "magic_level",
        "rank_scale",
        "skill_style",
        "proficiency_access",
        "new_skill_frequency",
        "system_style",
        "narration_detail",
    }
)

_LIST_FIELDS = frozenset(
    {
        "starter_equipment",
        "world_races",
        "custom_skills",
    }
)


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9'-]{2,}", _norm(text))
    return {w for w in words if w not in _STOP}


def _split_listish(raw: Any) -> list[str]:
    if isinstance(raw, list):
        parts = [str(x).strip() for x in raw]
    else:
        parts = re.split(r"[,;|]+", str(raw or ""))
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" .")
        if not p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p[:120])
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def text_similarity(a: str, b: str) -> float:
    """0..1 rough similarity for short setup phrases."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    return _jaccard(_tokens(na), _tokens(nb))


# --- finding helpers ---------------------------------------------------------

def _finding(
    *,
    sev: str,
    code: str,
    fields: list[str],
    detail: str,
    repair: str = "",
) -> dict[str, Any]:
    return {
        "sev": sev,  # bug | wrong | hole | pattern
        "code": code,
        "fields": fields,
        "detail": detail[:300],
        "repair": repair[:200],
    }


# --- checks ------------------------------------------------------------------

def check_list_duplicates(fields: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Dedupe comma-lists (equipment, races, custom_skills phrases)."""
    out = dict(fields)
    findings: list[dict[str, Any]] = []
    for field in _LIST_FIELDS:
        if field not in out:
            continue
        raw = out.get(field)
        if raw is None or raw == "":
            continue
        if field == "custom_skills":
            # custom_skills is prose-ish; still collapse exact duplicate clauses
            parts = _split_listish(raw)
            if len(parts) != len(set(p.lower() for p in parts)):
                # keep order, drop exact dups
                cleaned = _split_listish(parts)
                if ", ".join(cleaned).lower() != _norm(str(raw)).replace(";", ","):
                    findings.append(
                        _finding(
                            sev="pattern",
                            code="list_exact_duplicates",
                            fields=[field],
                            detail=f"Duplicate clauses removed from {field}",
                            repair="dedupe_clauses",
                        )
                    )
                    out[field] = ", ".join(cleaned)[:1200]
            # near-duplicate clauses
            near = []
            for i in range(len(parts)):
                for j in range(i + 1, len(parts)):
                    if text_similarity(parts[i], parts[j]) >= 0.82:
                        near.append((parts[i], parts[j]))
            if near:
                findings.append(
                    _finding(
                        sev="hole",
                        code="list_near_duplicate_clauses",
                        fields=[field],
                        detail=f"Near-duplicate clauses in {field}: {near[0][0]!r} ~ {near[0][1]!r}",
                    )
                )
            continue

        parts = _split_listish(raw)
        cleaned = _split_listish(parts)  # already unique by lower
        # Detect near-dups among equipment/races
        drop: set[int] = set()
        for i in range(len(cleaned)):
            if i in drop:
                continue
            for j in range(i + 1, len(cleaned)):
                if j in drop:
                    continue
                if text_similarity(cleaned[i], cleaned[j]) >= 0.85:
                    drop.add(j)
                    findings.append(
                        _finding(
                            sev="pattern",
                            code="list_near_duplicate_items",
                            fields=[field],
                            detail=f"Near-duplicate in {field}: kept {cleaned[i]!r}, dropped {cleaned[j]!r}",
                            repair="drop_weaker_near_dup",
                        )
                    )
        if drop:
            cleaned = [x for i, x in enumerate(cleaned) if i not in drop]
        new_val = ", ".join(cleaned)
        if _norm(new_val) != _norm(str(raw)):
            if not any(f["code"] == "list_near_duplicate_items" and field in f["fields"] for f in findings):
                findings.append(
                    _finding(
                        sev="pattern",
                        code="list_exact_duplicates",
                        fields=[field],
                        detail=f"Exact duplicate entries collapsed in {field}",
                        repair="dedupe",
                    )
                )
            out[field] = new_val[:500] if field != "custom_skills" else new_val[:1200]
    return out, findings


def check_ability_duplicates(fields: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize ability placeholders, diversify clone costs, near-dup engine."""
    out = dict(fields)
    findings: list[dict[str, Any]] = []
    abs_list = out.get("special_abilities")
    if not isinstance(abs_list, list):
        return out, findings
    origin = str(out.get("special_ability_origin") or "")
    # Always normalize each ability (prereq placeholders, lock policy)
    try:
        from app.llm import normalize_ability_lock_and_prerequisites

        cleaned_abs = []
        for ab in abs_list:
            if not isinstance(ab, dict):
                continue
            before_pr = str(ab.get("prerequisites") or "")
            nab = normalize_ability_lock_and_prerequisites(ab, origin=origin)
            after_pr = str(nab.get("prerequisites") or "")
            if before_pr in {"[]", "locked=true", "{}", "null", "true", "false"} and after_pr != before_pr:
                findings.append(
                    _finding(
                        sev="bug",
                        code="ability_prereq_placeholder",
                        fields=["special_abilities"],
                        detail=f"{nab.get('name')}: cleared {before_pr!r}",
                        repair="normalize_ability_lock_and_prerequisites",
                    )
                )
            cleaned_abs.append(nab)
        abs_list = cleaned_abs
        out["special_abilities"] = abs_list
    except Exception:
        abs_list = [a for a in abs_list if isinstance(a, dict)]
        out["special_abilities"] = abs_list

    # Cost clone spam (all "1 hour meditation to recharge")
    if len(abs_list) >= 2:
        try:
            from app.llm import _cost_structure_fingerprint, diversify_ability_costs

            fps = [_cost_structure_fingerprint(str(a.get("cost") or "")) for a in abs_list]
            uniq = {fp for fp in fps if fp}
            med_family = {
                "HOUR_MEDITATION_RECHARGE",
                "ONCE_PER_X_PLUS_HOUR_MEDITATION_RECHARGE",
                "HOUR_RITUAL_RECHARGE",
                "ONCE_DAY_PLUS_HOUR",
                "MAINTAIN_HOUR_ENV_DAILY",
                "ONCE_PER_RANK",
            }
            med_hits = sum(1 for fp in fps if fp in med_family)
            if len(uniq) <= 1 or med_hits >= 2:
                findings.append(
                    _finding(
                        sev="wrong",
                        code="ability_identical_or_meditation_cost_spam",
                        fields=["special_abilities"],
                        detail=f"cost fingerprints={fps[:6]}",
                        repair="diversify_ability_costs",
                    )
                )
                abs_list = diversify_ability_costs(abs_list, force=True)
                try:
                    from app.player_resources import diversify_resource_costs, magic_allows_mana
                    from app.llm import diversify_ability_prerequisites

                    magic_ok = magic_allows_mana(str(out.get("magic_level") or ""), out)
                    abs_list = diversify_resource_costs(abs_list, magic_ok=magic_ok, force=True)
                    abs_list = diversify_ability_prerequisites(
                        abs_list,
                        force=True,
                        origin=str(out.get("special_ability_origin") or ""),
                    )
                except Exception:
                    pass
                out["special_abilities"] = abs_list
        except Exception as exc:
            findings.append(
                _finding(
                    sev="hole",
                    code="ability_cost_diversify_unavailable",
                    fields=["special_abilities"],
                    detail=str(exc)[:200],
                )
            )

    if len(abs_list) < 2:
        return out, findings
    try:
        from app.llm import ensure_distinct_abilities, find_near_duplicate_pairs

        pairs = find_near_duplicate_pairs(abs_list)
        if not pairs:
            return out, findings
        findings.append(
            _finding(
                sev="wrong",
                code="ability_near_duplicates",
                fields=["special_abilities"],
                detail=f"Near-duplicate abilities: {pairs[0].get('names')} score={pairs[0].get('score')}",
                repair="ensure_distinct_abilities",
            )
        )
        dedupe = ensure_distinct_abilities(
            abs_list,
            origin=origin,
            use_llm=False,  # board sanitize is deterministic; LLM path runs at generate-time
            world_style=str(out.get("world_style") or ""),
            max_rounds=3,
        )
        if isinstance(dedupe.get("abilities"), list) and dedupe["abilities"]:
            # diversify costs again after remakes
            try:
                from app.llm import diversify_ability_costs

                out["special_abilities"] = diversify_ability_costs(dedupe["abilities"], force=False)
            except Exception:
                out["special_abilities"] = dedupe["abilities"]
            findings[-1]["repair"] = f"deduped_rounds={dedupe.get('rounds')}"
    except Exception as exc:
        findings.append(
            _finding(
                sev="hole",
                code="ability_dedupe_unavailable",
                fields=["special_abilities"],
                detail=str(exc)[:200],
            )
        )
    return out, findings


def check_slogan_patterns(fields: dict[str, Any], *, idea: str = "") -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Structure fields must not carry power-fantasy / idea slogans."""
    out = dict(fields)
    findings: list[dict[str, Any]] = []
    idea_l = _norm(idea)
    for field in _STRUCTURE_FIELDS:
        if field not in out:
            continue
        val = str(out.get(field) or "").strip()
        if not val:
            continue
        low = val.lower()
        bad = [m for m in _SLOGAN_MARKERS if m in low]
        # idea paste into short structure fields
        if idea_l and len(idea_l) > 24 and idea_l[:40] in low:
            bad.append("idea_paste")
        if field in {"world_style", "tone", "quest_style", "faction_pressure"} and len(val) > 90:
            bad.append("too_long_structure")
        if bad:
            findings.append(
                _finding(
                    sev="pattern",
                    code="structure_slogan_or_paste",
                    fields=[field],
                    detail=f"{field} contaminated ({', '.join(bad)}): {val[:80]!r}",
                    repair="structural_fallback",
                )
            )
            try:
                from app.setup_composer import structural_fallback

                fb = structural_fallback(field, {**out, "field": field})
                if fb is not None:
                    out[field] = fb
            except Exception:
                pass
    return out, findings


def check_cross_field_inconsistencies(fields: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Mode/memory/story, magic/world, modern gear, race rules, etc."""
    out = dict(fields)
    findings: list[dict[str, Any]] = []
    mode = _norm(out.get("backstory_mode"))
    memory = _norm(out.get("memory_policy"))
    story = _norm(out.get("character_backstory"))
    world = _norm(out.get("world_style"))
    tech = _norm(out.get("tech_level"))
    magic = _norm(out.get("magic_level"))
    gear = _norm(out.get("starter_equipment"))
    appearance = _norm(out.get("appearance"))
    races = _norm(out.get("world_races"))
    race_magic = _norm(out.get("race_magic_rules"))
    race_ability = _norm(out.get("race_ability_rules"))
    origin = _norm(out.get("special_ability_origin"))
    abilities = out.get("special_abilities") if isinstance(out.get("special_abilities"), list) else []

    # Memory vs backstory
    try:
        from app.setup_composer import memory_backstory_mismatch, resolve_memory_policy

        reasons = memory_backstory_mismatch(
            out.get("backstory_mode"),
            out.get("memory_policy"),
            out.get("character_backstory"),
        )
        if reasons:
            findings.append(
                _finding(
                    sev="hole",
                    code="memory_backstory_mismatch",
                    fields=["memory_policy", "backstory_mode", "character_backstory"],
                    detail=", ".join(reasons),
                    repair="resolve_memory_policy",
                )
            )
            fixed, _ = resolve_memory_policy(
                out.get("backstory_mode"),
                out.get("memory_policy"),
                out.get("character_backstory"),
            )
            if fixed is not None:
                out["memory_policy"] = fixed
    except Exception:
        pass

    # Prose mode still present
    if out.get("backstory_mode") and (
        len(str(out.get("backstory_mode"))) > 40 or str(out.get("backstory_mode")).count(" ") >= 6
    ):
        findings.append(
            _finding(
                sev="bug",
                code="backstory_mode_is_prose",
                fields=["backstory_mode"],
                detail=str(out.get("backstory_mode"))[:120],
                repair="normalize_backstory_mode",
            )
        )
        try:
            from app.setup_composer import normalize_backstory_mode

            out["backstory_mode"] = normalize_backstory_mode(
                out.get("backstory_mode"),
                story=str(out.get("character_backstory") or ""),
            )
        except Exception:
            pass

    # Internal stance clashes (magic is a tool + not wizardry, etc.)
    if story:
        try:
            from app.setup_composer import (
                backstory_self_contradictions,
                repair_backstory_self_contradictions,
            )

            clash = backstory_self_contradictions(str(out.get("character_backstory") or ""))
            if not clash.get("ok"):
                findings.append(
                    _finding(
                        sev="wrong",
                        code="backstory_self_contradiction",
                        fields=["character_backstory"],
                        detail=",".join(clash.get("hard") or clash.get("codes") or [])[:200],
                        repair="repair_backstory_self_contradictions",
                    )
                )
                out["character_backstory"] = repair_backstory_self_contradictions(
                    str(out.get("character_backstory") or ""),
                    magic_level=str(out.get("magic_level") or ""),
                    world_style=str(out.get("world_style") or world),
                )
                story = _norm(out.get("character_backstory"))
        except Exception:
            pass

    # Transmigrated must be former-world + transport + arrival start (not native fantasy plot)
    if "transmigrat" in mode and story:
        try:
            from app.setup_composer import (
                build_transmigration_backstory,
                ensure_isekai_arrival_beat,
                transmigration_story_score,
            )

            score = transmigration_story_score(str(out.get("character_backstory") or ""))
            if not score.get("ok"):
                findings.append(
                    _finding(
                        sev="wrong",
                        code="transmigrated_backstory_missing_origin_transport",
                        fields=["character_backstory", "backstory_mode"],
                        detail=(
                            f"former={score.get('has_former_world')} transport={score.get('has_transport')} "
                            f"native_hits={score.get('native_fantasy_plot_hits')} meta={score.get('skill_meta')} "
                            f"bolted={score.get('bolted_generic_arrival')} "
                            f"contradict={score.get('self_contradictions')}"
                        ),
                        repair="build_transmigration_backstory",
                    )
                )
                out["character_backstory"] = ensure_isekai_arrival_beat(
                    str(out.get("character_backstory") or ""),
                    mode=str(out.get("backstory_mode") or "transmigrated"),
                    idea=str(out.get("_randomize_idea") or ""),
                    world_style=str(out.get("world_style") or world),
                )
                if not transmigration_story_score(str(out.get("character_backstory") or "")).get("ok"):
                    out["character_backstory"] = build_transmigration_backstory(
                        old_story=str(out.get("character_backstory") or ""),
                        idea=str(out.get("_randomize_idea") or ""),
                        world_style=str(out.get("world_style") or world),
                    )
        except Exception:
            pass

    # Reincarnated without this-life
    if "reincarnat" in mode and story:
        if not any(m in story for m in ("grew up", "years", "child", "raised", "born in", "village", "childhood")):
            findings.append(
                _finding(
                    sev="hole",
                    code="reincarnated_missing_this_life",
                    fields=["character_backstory", "backstory_mode"],
                    detail="reincarnated mode without childhood/years-in-world beat",
                )
            )

    # Magic off but magic gear / abilities
    magic_off = any(x in magic for x in ("none", "no magic", "off", "absent", "zero"))
    if magic_off:
        if any(w in gear + " " + appearance for w in ("wand", "grimoire", "spell", "mana", "enchanted", "arcane")):
            findings.append(
                _finding(
                    sev="wrong",
                    code="magic_gear_in_no_magic_world",
                    fields=["starter_equipment", "appearance", "magic_level"],
                    detail="magical gear while magic_level is off",
                )
            )
        if origin not in {"", "none", "off"} and abilities:
            findings.append(
                _finding(
                    sev="hole",
                    code="abilities_with_magic_off",
                    fields=["special_ability_origin", "magic_level"],
                    detail="special abilities enabled while magic_level is none (may be non-magic powers — verify)",
                )
            )

    # Modern tech in low-tech fantasy (native)
    low_tech = any(t in tech + " " + world for t in ("medieval", "iron age", "bronze", "fantasy", "isekai", "cultivation"))
    modern_world = any(t in tech + " " + world for t in ("modern", "cyber", "near future", "sci-fi", "scifi", "space"))
    if low_tech and not modern_world:
        if any(w in gear + " " + appearance for w in ("smartphone", "laptop", "earbuds", "cyberdeck", "pistol")):
            if "transmigrat" not in mode and "isekai" not in world and "another world" not in story:
                findings.append(
                    _finding(
                        sev="wrong",
                        code="modern_tech_native_fantasy",
                        fields=["starter_equipment", "tech_level", "world_style"],
                        detail="modern tech gear without isekai/transmigration framing",
                    )
                )

    # Race rules invent peoples
    try:
        from app.setup_composer import race_rules_mismatch_reasons, rebuild_race_rules

        for field, text in (("race_magic_rules", race_magic), ("race_ability_rules", race_ability)):
            if not text or field not in out:
                continue
            reasons = race_rules_mismatch_reasons(out.get("world_races"), out.get(field))
            if reasons:
                findings.append(
                    _finding(
                        sev="wrong",
                        code="race_rules_people_mismatch",
                        fields=[field, "world_races"],
                        detail=", ".join(reasons),
                        repair="rebuild_race_rules",
                    )
                )
                out[field] = rebuild_race_rules(field, out.get("world_races"), out)
    except Exception:
        pass

    # Difficulty vs death_rules soft mismatch
    diff = _norm(out.get("difficulty"))
    death = _norm(out.get("death_rules"))
    if diff == "easy" and "permadeath" in death:
        findings.append(
            _finding(
                sev="hole",
                code="easy_with_permadeath",
                fields=["difficulty", "death_rules"],
                detail="easy difficulty with permadeath is a harsh combo",
            )
        )

    # Game system off but system style / skills assume windows
    if out.get("game_system") is False or _norm(out.get("game_system")) in {"false", "0", "no", "off"}:
        cs = _norm(out.get("custom_skills"))
        if "system ui" in cs or "status window" in cs:
            findings.append(
                _finding(
                    sev="hole",
                    code="system_ui_in_skills_while_game_system_off",
                    fields=["custom_skills", "game_system"],
                    detail="custom_skills mentions system UI while game_system is off",
                )
            )

    # Look fields: hair leaked into appearance / face
    hair = _norm(out.get("hair"))
    face = _norm(out.get("facial_features"))
    app = _norm(out.get("appearance"))
    if hair and app and hair in app:
        findings.append(
            _finding(
                sev="pattern",
                code="hair_leaked_into_appearance",
                fields=["hair", "appearance"],
                detail="hair phrase duplicated in appearance",
                repair="strip_hair_from_appearance",
            )
        )
        # strip once
        try:
            from app.setup_composer import normalize_look_fields

            fixed, _ = normalize_look_fields(out, context=out)
            out.update({k: fixed[k] for k in ("hair", "facial_features", "appearance") if k in fixed})
        except Exception:
            pass
    if face and "hair" in face:
        findings.append(
            _finding(
                sev="pattern",
                code="hair_in_facial_features",
                fields=["facial_features"],
                detail="facial_features contains hair wording",
            )
        )

    # First-person backstory
    story_raw = str(out.get("character_backstory") or "")
    if re.search(r"\bI\b|\bmy\b|\bI'm\b", story_raw) and not re.search(r"\bthey\b", story_raw, re.I):
        findings.append(
            _finding(
                sev="wrong",
                code="first_person_backstory",
                fields=["character_backstory"],
                detail="backstory uses first person",
                repair="rewrite_backstory_third_person",
            )
        )
        try:
            from app.setup_composer import rewrite_backstory_third_person

            out["character_backstory"] = rewrite_backstory_third_person(story_raw)
        except Exception:
            pass

    # Abilities present while origin none
    if origin in {"none", "off", "no", ""} and abilities:
        findings.append(
            _finding(
                sev="bug",
                code="abilities_with_origin_none",
                fields=["special_abilities", "special_ability_origin"],
                detail="special_abilities non-empty while origin is none",
                repair="clear_abilities",
            )
        )
        out["special_abilities"] = []

    # previous_life_age normalize
    if "previous_life_age" in out:
        try:
            from app.setup_composer import normalize_previous_life_age

            age = normalize_previous_life_age(out.get("previous_life_age"))
            if not any(m in mode for m in ("reincarnat", "transmigrat", "fragment")):
                age = ""
            if str(out.get("previous_life_age") or "") != age:
                findings.append(
                    _finding(
                        sev="pattern",
                        code="previous_life_age_normalized",
                        fields=["previous_life_age"],
                        detail=f"{out.get('previous_life_age')!r} -> {age!r}",
                        repair="normalize_previous_life_age",
                    )
                )
                out["previous_life_age"] = age
        except Exception:
            pass

    return out, findings


def check_internal_ability_quality_flags(fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Flag ability JSON placeholders without full quality gate cost."""
    findings: list[dict[str, Any]] = []
    abs_list = fields.get("special_abilities")
    if not isinstance(abs_list, list):
        return findings
    for ab in abs_list:
        if not isinstance(ab, dict):
            continue
        name = str(ab.get("name") or "").strip()
        desc = str(ab.get("description") or "").strip()
        prereq = str(ab.get("prerequisites") or "").strip()
        if name and desc and _norm(name) == _norm(desc):
            findings.append(
                _finding(
                    sev="bug",
                    code="ability_description_equals_name",
                    fields=["special_abilities"],
                    detail=name[:80],
                )
            )
        if prereq in {"[]", "{}", "null", "locked=true", "true", "false"}:
            findings.append(
                _finding(
                    sev="bug",
                    code="ability_prereq_placeholder",
                    fields=["special_abilities"],
                    detail=f"{name}: {prereq!r}",
                )
            )
        if bool(ab.get("locked")) and len(prereq) < 8:
            findings.append(
                _finding(
                    sev="hole",
                    code="ability_locked_without_prereq",
                    fields=["special_abilities"],
                    detail=name or "?",
                )
            )
    return findings


# --- public API --------------------------------------------------------------

def crosscheck_setup_fields(
    fields: dict[str, Any],
    *,
    idea: str = "",
    context: dict[str, Any] | None = None,
    repair: bool = True,
) -> dict[str, Any]:
    """
    Board-wide cross-check.

    Returns:
      {
        ok: bool,  # no bug/wrong findings (holes/patterns may remain)
        fields: repaired dict,
        findings: [...],
        summary: {bugs, wrong, holes, patterns},
      }
    """
    base = {k: v for k, v in (fields or {}).items() if not str(k).startswith("_")}
    merged = {**(context or {}), **base}
    idea_s = idea or str(merged.get("_randomize_idea") or merged.get("idea") or "")
    all_findings: list[dict[str, Any]] = []
    out = dict(base)

    if repair:
        out, f = check_list_duplicates(out)
        all_findings.extend(f)
        out, f = check_slogan_patterns(out, idea=idea_s)
        all_findings.extend(f)
        # Cross-field needs merged context for reads, writes only to out keys
        probe = {**merged, **out}
        probe, f = check_cross_field_inconsistencies(probe)
        all_findings.extend(f)
        for k in list(out.keys()) + [
            "memory_policy",
            "backstory_mode",
            "character_backstory",
            "special_abilities",
            "starter_equipment",
            "appearance",
            "hair",
            "facial_features",
            "race_magic_rules",
            "race_ability_rules",
            "world_style",
            "tone",
        ]:
            if k in probe:
                out[k] = probe[k]
        out, f = check_ability_duplicates(out)
        all_findings.extend(f)
    else:
        _, f = check_list_duplicates(out)
        all_findings.extend(f)
        _, f = check_slogan_patterns(out, idea=idea_s)
        all_findings.extend(f)
        _, f = check_cross_field_inconsistencies({**merged, **out})
        all_findings.extend(f)

    all_findings.extend(check_internal_ability_quality_flags(out))

    # Dedupe findings by code+fields+detail prefix
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in all_findings:
        key = f"{item.get('code')}|{','.join(item.get('fields') or [])}|{str(item.get('detail') or '')[:80]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    summary = {"bugs": 0, "wrong": 0, "holes": 0, "patterns": 0}
    for item in unique:
        sev = str(item.get("sev") or "hole")
        key = {"bug": "bugs", "wrong": "wrong", "hole": "holes", "pattern": "patterns"}.get(sev, "holes")
        summary[key] = int(summary.get(key) or 0) + 1

    ok = summary["bugs"] == 0 and summary["wrong"] == 0
    return {
        "ok": ok,
        "fields": out,
        "findings": unique,
        "summary": summary,
    }


def crosscheck_setup_matrix(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Run crosscheck on many setting packages; used by tests and audit tools."""
    rows = []
    totals = {"bugs": 0, "wrong": 0, "holes": 0, "patterns": 0, "cases": 0, "failed_cases": 0}
    for case in cases:
        name = str(case.get("id") or case.get("name") or f"case_{len(rows)}")
        fields = case.get("fields") if isinstance(case.get("fields"), dict) else case
        idea = str(case.get("idea") or "")
        result = crosscheck_setup_fields(fields, idea=idea, context=case.get("context"), repair=True)
        row = {
            "id": name,
            "ok": result["ok"],
            "summary": result["summary"],
            "findings": result["findings"],
            "fields": result["fields"],
        }
        rows.append(row)
        totals["cases"] += 1
        if not result["ok"]:
            totals["failed_cases"] += 1
        for k in ("bugs", "wrong", "holes", "patterns"):
            totals[k] = int(totals.get(k) or 0) + int(result["summary"].get(k) or 0)
    return {"cases": rows, "totals": totals}
