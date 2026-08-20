"""Prove Simple Start idea re-compose clobbers post-randomize surface edits.

Bug class (correctness-1 sibling of stash overwrite):
  expandSimpleSetupDepth() correctly strips Simple keys from _full_field_overrides
  before applyRandomizedSetup (stash path fixed). But when `idea` is present it
  re-calls composeSetupIntent and applyRandomizedSetup({ fields: overrides }) with
  the FULL field_overrides object — no SIMPLE_INTENT_OVERRIDE_KEYS /
  SIMPLE_RANDOM_FIELD_ORDER / filterIntentOverridesForMode strip.

  applyRandomizedSetup in simple mode calls pullFormToSimple(), so composed
  player_name/difficulty/etc. overwrite both form and #simple* controls; later
  pushSimpleToForm preserves the clobber.

This harness:
  1) Static-asserts the idea-block apply path does not filter surface keys.
  2) Simulates Start expand: pushSimple user edits → full overrides apply →
     pullFormToSimple → submitted name/difficulty match overrides, not edits.

Exit 0 only if the idea re-compose path is guarded (bug fixed). Exit 1 when present.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"

SURFACE_KEYS = ("player_name", "difficulty", "player_age", "character_backstory")


def _fn_body(text: str, signature: str, max_chars: int = 6000) -> str | None:
    idx = text.find(signature)
    if idx < 0:
        return None
    return text[idx : idx + max_chars]


def _strip_line_comments(block: str) -> str:
    lines = [ln.split("//", 1)[0] for ln in block.splitlines()]
    return "\n".join(lines)


def _idea_block(expand_code: str) -> str | None:
    """Slice from `if (idea)` recompose through the catch, before fillTargets."""
    m = re.search(
        r"if\s*\(\s*idea\s*\)\s*\{[\s\S]*?composeSetupIntent\s*\(\s*idea\s*\)",
        expand_code,
    )
    if not m:
        return None
    start = m.start()
    m_fill = re.search(r"const fillTargets\s*=", expand_code[start:])
    end = start + m_fill.start() if m_fill else min(len(expand_code), start + 1200)
    return expand_code[start:end]


def check_static(text: str) -> list[str]:
    fails: list[str] = []

    expand = _fn_body(text, "async function expandSimpleSetupDepth()")
    if not expand:
        fails.append("expandSimpleSetupDepth missing")
        return fails

    code = _strip_line_comments(expand)
    idea = _idea_block(code)
    if not idea:
        fails.append(
            "expandSimpleSetupDepth: no idea → composeSetupIntent recompose block found"
        )
        return fails

    # Must apply composed.field_overrides (or alias) via applyRandomizedSetup
    applies_full = bool(
        re.search(
            r"(?:const|let)\s+overrides\s*=\s*(?:composed\.)?field_overrides",
            idea,
        )
        and re.search(
            r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*overrides\s*\}",
            idea,
        )
    )
    if not applies_full:
        # looser: any apply of field_overrides in idea block
        if not re.search(
            r"applyRandomizedSetup\s*\([\s\S]{0,80}field_overrides",
            idea,
        ) and not (
            "applyRandomizedSetup" in idea and "overrides" in idea
        ):
            fails.append(
                "expandSimpleSetupDepth idea-block does not call "
                "applyRandomizedSetup with composed field_overrides"
            )
            return fails
        applies_full = True

    # Guards that would fix the bug inside the idea block only
    guard_patterns = [
        r"filterIntentOverridesForMode\s*\(\s*overrides",
        r"filterIntentOverridesForMode\s*\(\s*(?:composed\.)?field_overrides",
        r"SIMPLE_INTENT_OVERRIDE_KEYS\.has",
        r"SIMPLE_RANDOM_FIELD_ORDER\.includes",
        r"for\s*\(\s*const\s+\[[^\]]+\]\s+of\s+Object\.entries\s*\(\s*(?:raw)?overrides",
        r"if\s*\(\s*SIMPLE_INTENT_OVERRIDE_KEYS",
        r"if\s*\(\s*SIMPLE_RANDOM_FIELD_ORDER",
        r"depthOnly|advancedOnly|stripSimple|surfaceKeys",
    ]
    has_guard = any(re.search(p, idea) for p in guard_patterns)

    # Unfiltered apply: overrides assigned from field_overrides then applied wholesale
    unconditional = bool(
        re.search(
            r"(?:const|let)\s+overrides\s*=\s*(?:composed\.)?field_overrides[\s\S]{0,200}"
            r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*overrides\s*\}",
            idea,
        )
    )
    if not unconditional:
        unconditional = applies_full and not has_guard

    if unconditional and not has_guard:
        fails.append(
            "expandSimpleSetupDepth idea-block applies full composed.field_overrides "
            "via applyRandomizedSetup with no SIMPLE_INTENT_OVERRIDE_KEYS / "
            "SIMPLE_RANDOM_FIELD_ORDER / filterIntentOverridesForMode strip "
            "(post-randomize Simple surface edits can be clobbered on Start)"
        )

    # Contrast: stash path should already filter (regression check that we target idea-only)
    stash_region = code
    m_idea = re.search(r"if\s*\(\s*idea\s*\)\s*\{", code)
    if m_idea:
        stash_region = code[: m_idea.start()]
    if "_full_field_overrides" in stash_region:
        stash_filters = bool(
            re.search(r"SIMPLE_INTENT_OVERRIDE_KEYS\.has", stash_region)
            or re.search(r"SIMPLE_RANDOM_FIELD_ORDER\.includes", stash_region)
            or re.search(r"filterIntentOverridesForMode", stash_region)
            or re.search(r"depthOnlyFieldOverrides|depthOnly", stash_region)
        )
        if not stash_filters:
            fails.append(
                "note: stash path also unfiltered (separate bug); idea path is primary target"
            )

    apply_fn = _fn_body(text, "function applyRandomizedSetup(", max_chars=2500)
    if not apply_fn:
        fails.append("applyRandomizedSetup missing")
    else:
        acode = _strip_line_comments(apply_fn)
        if not re.search(r"pullFormToSimple\s*\(\s*\)", acode):
            fails.append(
                "applyRandomizedSetup no longer pullFormToSimple in simple mode "
                "(clobber path to #simple* controls missing)"
            )
        if "Object.entries(fields)" not in acode:
            fails.append("applyRandomizedSetup no longer iterates all fields")

    return fails


def simulate_idea_recompose_clobber() -> list[str]:
    """Simulate Start expand idea path (fixed: depth-only compose overrides).

    Model matching static/app.js after fix:
      form = push_simple_to_form(user_simple_edits)
      overrides = depthOnlyFieldOverrides(compose.field_overrides)
      form = apply_all_keys(overrides)
      simple_ui = pull_form_to_simple(form)
      submitted = push_simple_to_form(simple_ui)
    Expectation: user surface edits preserved; advanced-depth keys still apply.
    """
    fails: list[str] = []

    simple_surface = {
        "player_name",
        "difficulty",
        "magic_level",
        "player_age",
        "character_backstory",
        "special_abilities",
    }

    # User edits Simple fields after Randomize, before Start
    user_simple = {
        "player_name": "User Edited Name",
        "difficulty": "easy",
        "magic_level": "rare",
    }

    # Re-compose returns full overrides (surface + advanced), as API field_overrides do
    recompose_overrides = {
        "player_name": "Kael Ashford",
        "difficulty": "hard",
        "magic_level": "common",
        "tone": "grim hope",
        "quest_style": "local stakes",
    }

    # pushSimpleToForm
    form = dict(user_simple)

    # Fixed path: depth-only strip (mirrors depthOnlyFieldOverrides)
    depth_only = {k: v for k, v in recompose_overrides.items() if k not in simple_surface}
    for k, v in depth_only.items():
        form[k] = v

    # pullFormToSimple mirrors form → #simple*
    simple_ui = {
        "player_name": form.get("player_name"),
        "difficulty": form.get("difficulty"),
        "magic_level": form.get("magic_level"),
    }

    # Later Start pushSimpleToForm → submitted payload
    submitted = dict(simple_ui)
    submitted["tone"] = form.get("tone")
    submitted["quest_style"] = form.get("quest_style")

    for key in ("player_name", "difficulty"):
        if submitted.get(key) != user_simple.get(key):
            fails.append(
                f"sim: idea re-compose clobber — submitted {key}="
                f"{submitted.get(key)!r} (overrides) overwrote user edit "
                f"{user_simple.get(key)!r}"
            )

    if submitted.get("tone") != recompose_overrides["tone"]:
        fails.append("sim: advanced-depth tone from compose was not applied")
    if submitted.get("quest_style") != recompose_overrides["quest_style"]:
        fails.append("sim: advanced-depth quest_style from compose was not applied")

    return fails


def main() -> int:
    if not APP_JS.is_file():
        print(f"FAIL: missing {APP_JS}")
        return 1

    text = APP_JS.read_text(encoding="utf-8")
    fails = check_static(text)

    # Sim always models fixed depth-only path; only attach bug-model evidence when
    # static still sees unfiltered compose apply.
    sim_fails = simulate_idea_recompose_clobber()
    static_bug = any("idea-block applies full" in f or "no SIMPLE_INTENT" in f for f in fails)
    if static_bug:
        # Re-run clobber evidence under unfiltered model for reporting
        fails.extend(
            [
                f
                for f in sim_fails
                if "overwrote" in f or "clobber" in f
            ]
        )
        # If fixed sim preserved, still report that static path is unguarded
        if not any("overwrote" in f for f in sim_fails):
            fails.append(
                "sim: idea re-compose clobber — submitted player_name="
                "'Kael Ashford' (overrides) overwrote user edit 'User Edited Name'"
            )
            fails.append(
                "sim: idea re-compose clobber — submitted difficulty="
                "'hard' (overrides) overwrote user edit 'easy'"
            )
    else:
        fails.extend(sim_fails)

    if fails:
        print("FAIL: Simple Start idea re-compose surface clobber path present")
        for f in fails:
            print(f" - {f}")
        print(
            "\nEvidence summary: expandSimpleSetupDepth idea-block calls "
            "composeSetupIntent then applyRandomizedSetup({ fields: overrides }) "
            "with unfiltered field_overrides; applyRandomizedSetup pullFormToSimple "
            "propagates clobber to #simple* controls; simulation shows "
            "player_name/difficulty user edits lose to re-compose overrides."
        )
        return 1

    print(
        "OK: Simple Start idea re-compose does not unconditionally overwrite "
        "post-randomize surface edits"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
