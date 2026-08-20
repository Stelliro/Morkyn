"""Prove expandSimpleSetupDepth fillTargets re-rolls Simple surface enums.

Bug class (correctness-2):
  expandSimpleSetupDepth() fillTargets includes magic_level, death_rules, and
  world_style (Simple-visible / Simple-randomize surface). Substantial-skip exists
  only for prose-ish keys (backstory length, hair≥12, etc.); enums have no
  non-empty / user-preserve guard. randomizeFieldApplies always returns true for
  these names. randomizeField → applyRandomizedSetup → pullFormToSimple in Simple
  mode, so re-rolls also overwrite #simpleMagicLevel / #simpleDeathRules /
  #simpleWorld. Later pushSimpleToForm cannot restore the user's Simple choices;
  startGame submits the re-rolled form values.

This harness:
  1) Static-asserts fillTargets lists surface enums with no non-empty skip.
  2) Static-asserts randomizeFieldApplies has no gate for those names.
  3) Static-asserts applyRandomizedSetup pullFormToSimple in simple mode.
  4) Simulates Start expand: user magic_level='none' etc. → fill always rewrites.

Exit 0 only if the re-roll path is guarded (bug fixed). Exit 1 when the bug is present.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"

SURFACE_ENUMS = ("magic_level", "death_rules", "world_style")


def _fn_body(text: str, signature: str, max_chars: int = 6000) -> str | None:
    idx = text.find(signature)
    if idx < 0:
        return None
    return text[idx : idx + max_chars]


def _strip_line_comments(block: str) -> str:
    lines = [ln.split("//", 1)[0] for ln in block.splitlines()]
    return "\n".join(lines)


def _extract_fill_targets(expand_code: str) -> list[str] | None:
    m = re.search(
        r"const\s+fillTargets\s*=\s*\[([\s\S]*?)\];",
        expand_code,
    )
    if not m:
        return None
    return re.findall(r'["\']([a-z_]+)["\']', m.group(1))


def _fill_loop_region(expand_code: str) -> str:
    """Body of for (const name of fillTargets) { ... } roughly."""
    m = re.search(r"for\s*\(\s*const\s+name\s+of\s+fillTargets\s*\)\s*\{", expand_code)
    if not m:
        return ""
    start = m.end()
    # brace match
    depth = 1
    i = start
    while i < len(expand_code) and depth:
        c = expand_code[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return expand_code[start : i - 1]


def check_static(text: str) -> list[str]:
    fails: list[str] = []

    expand = _fn_body(text, "async function expandSimpleSetupDepth()", max_chars=7000)
    if not expand:
        fails.append("expandSimpleSetupDepth missing")
        return fails

    code = _strip_line_comments(expand)
    targets = _extract_fill_targets(code)
    if targets is None:
        fails.append("fillTargets array not found in expandSimpleSetupDepth")
        return fails

    for name in SURFACE_ENUMS:
        if name not in targets:
            fails.append(f"fillTargets does not include Simple-surface enum {name!r}")

    loop = _fill_loop_region(code)
    if not loop:
        fails.append("fillTargets for-loop missing")
        return fails

    # Substantial-skip branches that exist today (prose / special cases only).
    prose_skips = {
        "special_abilities",
        "character_backstory",
        "custom_style",
        "starter_equipment",
        "appearance",
        "hair",
        "facial_features",
        "start_location",
    }
    # Detect per-name skip guards for surface enums:
    #   else if (name === "magic_level") { ... continue; }
    #   or if (name === "magic_level" && ...) continue;
    #   or generic non-empty: if (v) continue for all remaining names
    for name in SURFACE_ENUMS:
        # name === "magic_level" ... continue
        named_guard = re.search(
            rf'name\s*===\s*["\']{re.escape(name)}["\'][\s\S]{{0,220}}continue',
            loop,
        )
        # Array includes / Set has style for surface enums
        set_guard = re.search(
            rf'(?:SIMPLE_RANDOM_FIELD_ORDER|SIMPLE_INTENT_OVERRIDE_KEYS|surface)'
            rf'[\s\S]{{0,80}}(?:includes|has)\s*\(\s*name\s*\)[\s\S]{{0,120}}continue',
            loop,
            flags=re.I,
        )
        # Generic non-empty for select/enum after reading form value (applies to all names
        # without a specific branch) — only count if it is not nested under prose ifs only.
        generic_nonempty = re.search(
            r'else\s*\{\s*'
            r'(?:const\s+\w+\s*=\s*String\s*\([\s\S]{0,120}?\)\.trim\(\)\s*;\s*)?'
            r'if\s*\(\s*\w+\s*\)\s*continue',
            loop,
        ) or re.search(
            r'if\s*\(\s*name\s*!==\s*["\']special_abilities["\'][\s\S]{0,200}'
            r'String\s*\([\s\S]{0,120}?\)\.trim\(\)[\s\S]{0,80}continue',
            loop,
        )

        if named_guard or set_guard or generic_nonempty:
            # Guard present → this enum is protected (not a failure for this bug)
            continue

        # Confirm randomizeField is still called for unguarded names
        if "randomizeField" not in loop and "fallbackRandomizeField" not in loop:
            fails.append("fillTargets loop no longer calls randomizeField")
        else:
            fails.append(
                f"fillTargets re-rolls {name!r} with no non-empty / Simple-surface skip "
                f"(only prose skips: {sorted(prose_skips)})"
            )

    # randomizeFieldApplies: always true for surface enums
    applies = _fn_body(text, "function randomizeFieldApplies(", max_chars=1200)
    if not applies:
        fails.append("randomizeFieldApplies missing")
    else:
        acode = _strip_line_comments(applies)
        for name in SURFACE_ENUMS:
            if re.search(rf'["\']{re.escape(name)}["\']', acode):
                # Special-cased — may skip; not our failure
                pass
        # Must end with return true (default apply)
        if not re.search(r"return\s+true\s*;", acode):
            fails.append("randomizeFieldApplies does not default to return true")

    # applyRandomizedSetup pullFormToSimple in simple mode → Simple UI overwritten
    apply_fn = _fn_body(text, "function applyRandomizedSetup(", max_chars=2500)
    if not apply_fn:
        fails.append("applyRandomizedSetup missing")
    else:
        ap = _strip_line_comments(apply_fn)
        if "pullFormToSimple" not in ap:
            fails.append(
                "applyRandomizedSetup no longer pullFormToSimple in Simple mode "
                "(clobber path shape changed)"
            )
        elif not re.search(
            r"setupUiMode\s*===\s*[\"']simple[\"'][\s\S]{0,120}pullFormToSimple",
            ap,
        ):
            # Still has pullFormToSimple somewhere — count as mirror risk
            fails.append(
                "applyRandomizedSetup has pullFormToSimple but not clearly gated on "
                "setupUiMode === 'simple' (verify Simple UI mirror on apply)"
            )

    # Surface enums are Simple-randomize fields (product surface)
    for order_sig in ("const SIMPLE_RANDOM_FIELD_ORDER =", "SIMPLE_INTENT_OVERRIDE_KEYS"):
        chunk = _fn_body(text, order_sig, max_chars=2000) or ""
        if not chunk:
            # try alternate for Set
            if "SIMPLE_INTENT_OVERRIDE_KEYS" in order_sig:
                m = re.search(
                    r"const\s+SIMPLE_INTENT_OVERRIDE_KEYS\s*=\s*new\s+Set\s*\(\s*\[([\s\S]*?)\]\s*\)",
                    text,
                )
                chunk = m.group(0) if m else ""
            else:
                fails.append(f"{order_sig!r} missing")
                continue
        for name in ("magic_level", "death_rules"):
            if f'"{name}"' not in chunk and f"'{name}'" not in chunk:
                fails.append(f"{order_sig} missing Simple surface key {name!r}")
        # world_style is surface via SIMPLE_RANDOM_FIELD_ORDER
        if "SIMPLE_RANDOM_FIELD_ORDER" in order_sig:
            if '"world_style"' not in chunk and "'world_style'" not in chunk:
                fails.append("SIMPLE_RANDOM_FIELD_ORDER missing world_style")

    return fails


def simulate_filltargets_reroll() -> list[str]:
    """Pure simulation of Start expand fillTargets semantics (current product).

    Model (buggy):
      simple_ui = user choices
      form = push_simple_to_form(simple_ui)
      for name in fill_targets:
        if name in prose_skips_with_threshold and substantial: continue
        # enums: always randomize
        form[name] = random_value(name)  # ≠ user when pool has alternatives
        simple_ui = pull_form_to_simple(form)  # applyRandomizedSetup mirror
      form = push_simple_to_form(simple_ui)  # cannot restore original user enums
      submitted = form
    Expectation if fixed: submitted magic_level/death_rules/world_style == user simple.
    """
    fails: list[str] = []

    # User deliberately chose non-default Simple surface enums before Start
    user_simple = {
        "magic_level": "none",
        "death_rules": "permadeath threat",
        "world_style": "rain-slick megacity with wet neon markets",
        "custom_style": "rain-slick megacity with wet neon markets",
    }
    # RANDOM_SETUP pools (subset) — re-roll must be allowed to differ
    pools = {
        "magic_level": ["rare", "forbidden", "common utility", "cultivation", "none"],
        "death_rules": [
            "downed, not deleted",
            "lasting injuries",
            "permadeath threat",
            "narrative setback",
        ],
        "world_style": ["frontier dark fantasy", "grimdark city", "cultivation frontier"],
    }

    form = dict(user_simple)
    simple_ui = dict(user_simple)

    # fillTargets subset relevant to this candidate
    fill_targets = list(SURFACE_ENUMS)
    # Mirrors app.js substantial-skip: none of these apply to the three enums
    substantial_skip_names = {
        "special_abilities",
        "character_backstory",
        "custom_style",
        "starter_equipment",
        "appearance",
        "hair",
        "facial_features",
        "start_location",
    }

    def randomize_field(name: str) -> str:
        # Deterministic "re-roll": first pool value that differs from current
        cur = str(form.get(name) or "").strip().lower()
        for p in pools[name]:
            if p.strip().lower() != cur:
                return p
        return pools[name][0]

    for name in fill_targets:
        if name in substantial_skip_names:
            # would evaluate thresholds; enums are not in this set
            continue
        # No non-empty guard for enums → always rewrite
        form[name] = randomize_field(name)
        # applyRandomizedSetup → pullFormToSimple
        simple_ui[name] = form[name]
        if name == "world_style":
            simple_ui["custom_style"] = form[name]

    # Later pushSimpleToForm — pushes corrupted Simple UI
    form = dict(simple_ui)
    submitted = form

    for key in SURFACE_ENUMS:
        if submitted.get(key) == user_simple.get(key):
            fails.append(
                f"sim: expected re-roll of {key} to differ from user "
                f"{user_simple.get(key)!r} but submitted still matches "
                f"(simulation may be wrong)"
            )
        elif submitted.get(key) != user_simple.get(key):
            # This is the bug evidence: user surface value was lost
            fails.append(
                f"sim: Start submitted {key}={submitted.get(key)!r} "
                f"overwrote Simple user choice {user_simple.get(key)!r} "
                f"(fillTargets re-roll + pullFormToSimple clobber)"
            )

    return fails


def main() -> int:
    if not APP_JS.is_file():
        print(f"FAIL: missing {APP_JS}")
        return 1

    text = APP_JS.read_text(encoding="utf-8")
    static_fails = check_static(text)
    sim_fails = simulate_filltargets_reroll()

    # Simulation alone always models the bug; only count sim fails when static
    # confirms the unguarded path is present.
    unguarded = any("re-rolls" in f and "no non-empty" in f for f in static_fails)
    fails = list(static_fails)
    if unguarded:
        fails.extend(sim_fails)
    elif sim_fails and not static_fails:
        # Guards present → sim models old bug; do not fail
        pass

    if fails:
        print("FAIL: Simple Start fillTargets re-rolls surface enums")
        for f in fails:
            print(f" - {f}")
        print(
            "\nEvidence summary: expandSimpleSetupDepth fillTargets includes "
            "magic_level, death_rules, world_style without non-empty/surface skip; "
            "randomizeFieldApplies defaults true; applyRandomizedSetup pullFormToSimple "
            "in Simple mode so re-rolls clobber #simple* controls before final submit."
        )
        return 1

    print(
        "OK: Simple Start fillTargets does not unconditionally re-roll "
        "Simple-surface enums (magic_level / death_rules / world_style)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
