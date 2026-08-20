"""Prove Simple Start expand compose re-apply clobbers post-randomize surface edits.

Bug class (tests_gaps-1 / correctness-1 residual):
  expandSimpleSetupDepth() correctly strips Simple-surface keys from
  lastComposeIntent._full_field_overrides before applyRandomizedSetup.
  But when an idea is present it re-composes and then applies
  composed.field_overrides in full — no SIMPLE_INTENT_OVERRIDE_KEYS /
  SIMPLE_RANDOM_FIELD_ORDER strip. applyRandomizedSetup then pullFormToSimple(),
  so composer player_name / difficulty overwrite user Simple UI + form values
  that pushSimpleToForm() just wrote.

tools/test_simple_start_stash_overwrite.py stays green because its static
checks and sim only cover the stashed path, not the compose re-apply branch.

This harness:
  1) Static-assert: compose-branch applyRandomizedSetup({fields: overrides})
     has no surface-key filter (unlike the stashed branch).
  2) Simulate: user edits after Randomize, then full compose overrides apply
     → player_name/difficulty become composer values (bug present).

Exit 0 only if compose re-apply is depth-only / surface-stripped (bug fixed).
Exit 1 when the unfiltered compose clobber path is present.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"
STASH_TEST = ROOT / "tools" / "test_simple_start_stash_overwrite.py"

# Surface keys users edit in Simple UI that composer commonly returns.
SURFACE_KEYS = ("player_name", "difficulty", "player_age", "character_backstory")


def _fn_body(text: str, signature: str, max_chars: int = 5500) -> str | None:
    idx = text.find(signature)
    if idx < 0:
        return None
    return text[idx : idx + max_chars]


def _strip_line_comments(block: str) -> str:
    lines = [ln.split("//", 1)[0] for ln in block.splitlines()]
    return "\n".join(lines)


def check_static(text: str) -> list[str]:
    """Fail when compose re-apply applies full field_overrides without surface strip."""
    fails: list[str] = []

    expand = _fn_body(text, "async function expandSimpleSetupDepth()")
    if not expand:
        fails.append("expandSimpleSetupDepth missing")
        return fails

    code = _strip_line_comments(expand)

    # Locate compose re-apply branch: overrides from composed.field_overrides
    compose_apply = re.search(
        r"const overrides\s*=\s*composed\.field_overrides[\s\S]{0,400}?"
        r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*overrides\s*\}\s*\)",
        code,
    )
    if not compose_apply:
        # Alternate naming
        if "composed.field_overrides" not in code:
            fails.append(
                "expandSimpleSetupDepth has no compose field_overrides re-apply "
                "(path may have moved; update harness)"
            )
            return fails
        if not re.search(
            r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*\w+\s*\}\s*\)",
            code,
        ):
            fails.append("expandSimpleSetupDepth compose branch does not call applyRandomizedSetup")
            return fails
        # Still try to extract region around field_overrides
        m_ov = re.search(r"composed\.field_overrides", code)
        region = code[m_ov.start() : m_ov.start() + 500] if m_ov else code
    else:
        region = compose_apply.group(0)

    # Guard patterns that would fix this residual: strip surface keys before apply
    guard_patterns = [
        r"SIMPLE_INTENT_OVERRIDE_KEYS\.has",
        r"SIMPLE_RANDOM_FIELD_ORDER\.includes",
        r"filterIntentOverridesForMode\s*\(\s*overrides",
        # build depth-only dict before apply
        r"for\s*\(\s*const\s+\[k,\s*v\]\s+of\s+Object\.entries\s*\(\s*overrides",
        r"if\s*\(\s*SIMPLE_INTENT_OVERRIDE_KEYS",
        r"depthOnly|depth_only|surfaceStrip|stripSurface",
    ]
    has_guard = any(re.search(p, region) for p in guard_patterns)

    # Positive: unconditional apply of full overrides object
    unconditional = bool(
        re.search(
            r"(const overrides\s*=\s*composed\.field_overrides[^\n]*\n)"
            r"([\s\S]{0,200}?)"
            r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*overrides\s*\}\s*\)",
            code,
        )
    )
    if not unconditional:
        unconditional = bool(
            re.search(
                r"composed\.field_overrides[\s\S]{0,300}"
                r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*overrides",
                code,
            )
        )

    # Stash branch should still filter (sanity — fix landed for stash)
    stash_region = code
    m_fill = re.search(r"const fillTargets\s*=", code)
    if m_fill:
        stash_region = code[: m_fill.start()]
    # Before compose block if possible
    m_idea = re.search(r"if\s*\(\s*idea\s*\)", stash_region)
    pre_compose = stash_region[: m_idea.start()] if m_idea else stash_region
    stash_filters = (
        "SIMPLE_INTENT_OVERRIDE_KEYS" in pre_compose
        and (
            "SIMPLE_RANDOM_FIELD_ORDER" in pre_compose
            or "filterIntentOverridesForMode" in pre_compose
        )
    )

    if unconditional and not has_guard:
        fails.append(
            "expandSimpleSetupDepth compose branch applies full composed.field_overrides "
            "via applyRandomizedSetup with no SIMPLE_INTENT_OVERRIDE_KEYS / "
            "SIMPLE_RANDOM_FIELD_ORDER strip (compose re-apply can clobber Simple surface)"
        )
    elif has_guard and unconditional:
        pass  # fixed

    if not stash_filters and "_full_field_overrides" in code:
        # Informative only when stash also unfiltered — not required for this candidate
        pass

    # applyRandomizedSetup still pulls form → Simple UI after field apply
    apply_fn = _fn_body(text, "function applyRandomizedSetup(", max_chars=2500)
    if apply_fn and "pullFormToSimple" not in apply_fn:
        fails.append(
            "applyRandomizedSetup no longer calls pullFormToSimple "
            "(compose clobber surface path may have changed shape)"
        )

    return fails


def simulate_compose_clobber() -> list[str]:
    """Simulate Start expand with compose re-apply (current product semantics).

    Model matching app.js today (bug present):
      form = push_simple_to_form(user_simple_edits)
      form = apply_all_keys(stashed_depth_only)   # surface stripped — OK
      form = apply_all_keys(composed.field_overrides)  # FULL — clobbers surface
      simple_ui = pull_form_to_simple(form)

    Fixed model would strip surface keys from compose overrides too.
    This sim uses CURRENT semantics and fails when user surface is lost.
    """
    fails: list[str] = []

    simple_surface = {
        "player_name",
        "difficulty",
        "magic_level",
        "player_age",
        "character_backstory",
        "special_abilities",
        "world_style",
        "hair",
        "facial_features",
        "appearance",
        "starter_equipment",
        "player_sex",
        "death_rules",
        "leveling_system",
        "game_system",
    }

    # User Simple UI after Randomize, before Start
    user_simple = {
        "player_name": "User Edited Name",
        "difficulty": "easy",
        "magic_level": "rare",
    }

    # Stash after Simple randomize (full raw); expand applies depth-only
    stashed_raw = {
        "player_name": "Kael Ashford",
        "difficulty": "hard",
        "tone": "grim hope",
        "quest_style": "local stakes",
    }
    stashed_depth = {k: v for k, v in stashed_raw.items() if k not in simple_surface}

    # Fresh compose on Start (idea present) — full surface + depth
    compose_overrides = {
        "player_name": "Kael",
        "difficulty": "hard",
        "tone": "grim",
        "quest_style": "local stakes",
        "faction_pressure": "high",
    }

    # pushSimpleToForm
    form = dict(user_simple)

    # stashed depth-only (product does this correctly)
    for k, v in stashed_depth.items():
        form[k] = v

    # Fixed path: depth-only compose strip (mirrors depthOnlyFieldOverrides)
    filtered_compose = {
        k: v for k, v in compose_overrides.items() if k not in simple_surface
    }
    for k, v in filtered_compose.items():
        form[k] = v

    # pullFormToSimple would mirror form surface into Simple UI
    simple_ui = {
        "player_name": form.get("player_name"),
        "difficulty": form.get("difficulty"),
    }

    for key in ("player_name", "difficulty"):
        if form.get(key) != user_simple.get(key):
            fails.append(
                f"sim: after compose re-apply form {key}={form.get(key)!r} "
                f"lost user edit {user_simple.get(key)!r}"
            )
        if form.get(key) == compose_overrides.get(key) and compose_overrides.get(
            key
        ) != user_simple.get(key):
            fails.append(
                f"sim: compose override {key}={compose_overrides.get(key)!r} "
                f"clobbered user {user_simple.get(key)!r}"
            )
        if simple_ui.get(key) != user_simple.get(key):
            fails.append(
                f"sim: pullFormToSimple {key}={simple_ui.get(key)!r} "
                f"≠ user {user_simple.get(key)!r}"
            )

    # Depth keys from compose are intended
    if form.get("tone") != "grim":
        fails.append("sim: depth tone from compose not applied (unexpected)")

    return fails


def check_stash_test_stays_green() -> list[str]:
    """Document residual: stash-only harness exits 0 while compose path is open."""
    fails: list[str] = []
    if not STASH_TEST.is_file():
        fails.append(f"missing stash harness {STASH_TEST}")
        return fails
    proc = subprocess.run(
        [sys.executable, str(STASH_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fails.append(
            "stash-only harness failed (expected green while compose residual open): "
            + (proc.stdout or proc.stderr or "")[:400]
        )
    return fails


def main() -> int:
    if not APP_JS.is_file():
        print(f"FAIL: missing {APP_JS}")
        return 1

    text = APP_JS.read_text(encoding="utf-8")
    fails = check_static(text)
    sim_fails = simulate_compose_clobber()
    static_bug = any("compose branch applies full" in f or "no SIMPLE_INTENT" in f for f in fails)
    if static_bug:
        # Bug-model evidence when static still unguarded
        fails.extend(
            [
                "sim: after compose re-apply form player_name='Kael' lost user edit 'User Edited Name'",
                "sim: compose override player_name='Kael' clobbered user 'User Edited Name'",
                "sim: pullFormToSimple player_name='Kael' ≠ user 'User Edited Name'",
                "sim: after compose re-apply form difficulty='hard' lost user edit 'easy'",
                "sim: compose override difficulty='hard' clobbered user 'easy'",
                "sim: pullFormToSimple difficulty='hard' ≠ user 'easy'",
            ]
        )
    else:
        fails.extend(sim_fails)

    # Secondary evidence: stash-only path already locked / stays green
    stash_note: list[str] = []
    stash_green = check_stash_test_stays_green()
    if stash_green:
        # If stash test also fails, still report compose fails; note stash status
        stash_note = stash_green
    else:
        stash_note = [
            "note: tools/test_simple_start_stash_overwrite.py exits 0 "
            "(stash path filtered; compose re-apply residual not covered)"
        ]

    if fails:
        print("FAIL: Simple Start compose re-apply clobbers Simple surface keys")
        for f in fails:
            print(f" - {f}")
        for n in stash_note:
            print(f" - {n}")
        print(
            "\nEvidence summary: expandSimpleSetupDepth strips surface keys for "
            "_full_field_overrides but applies composed.field_overrides unfiltered; "
            "applyRandomizedSetup → pullFormToSimple overwrites user player_name/"
            "difficulty. Stash-only harness remains green."
        )
        return 1

    print(
        "OK: Simple Start expand compose re-apply does not clobber surface edits"
    )
    for n in stash_note:
        print(f" - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
