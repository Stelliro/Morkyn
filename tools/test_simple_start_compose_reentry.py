"""Prove Simple Start compose re-entry can re-clobber Simple-surface edits.

Bug class (robustness-2):
  expandSimpleSetupDepth() strips Simple-surface keys from stashed
  _full_field_overrides before applyRandomizedSetup — but after pushSimpleToForm
  it still awaits composeSetupIntent(idea) and applies composed.field_overrides
  RAW (no SIMPLE_INTENT_OVERRIDE_KEYS / SIMPLE_RANDOM_FIELD_ORDER filter).

  On Start re-entry with an idea (network compose succeeds), async compose can
  overwrite user-edited player_name/difficulty/etc. that the stash guard just
  preserved. tools/test_simple_start_stash_overwrite.py can stay green while
  this second path still clobbers.

This harness:
  1) Static-asserts the compose-reentry region in expandSimpleSetupDepth applies
     field_overrides without the same surface-key strip as the stash path.
  2) Simulates: pushSimpleToForm user values → raw compose overrides apply →
     surface keys lose to composer values.

Exit 0 only if the compose re-entry path is guarded (bug fixed). Exit 1 when present.
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


def _compose_region(expand_code: str) -> str | None:
    """Slice from composeSetupIntent call through apply of its overrides (before fillTargets)."""
    m = re.search(r"composeSetupIntent\s*\(\s*idea\s*\)", expand_code)
    if not m:
        return None
    rest = expand_code[m.start() :]
    m_fill = re.search(r"const fillTargets\s*=", rest)
    if m_fill:
        rest = rest[: m_fill.start()]
    return rest


def check_static(text: str) -> list[str]:
    fails: list[str] = []

    expand = _fn_body(text, "async function expandSimpleSetupDepth()")
    if not expand:
        fails.append("expandSimpleSetupDepth missing")
        return fails

    code = _strip_line_comments(expand)
    region = _compose_region(code)
    if not region:
        fails.append(
            "expandSimpleSetupDepth: no composeSetupIntent(idea) re-entry region found"
        )
        return fails

    # Must apply field_overrides from compose result
    applies_raw = bool(
        re.search(
            r"(?:const|let|var)\s+overrides\s*=\s*(?:composed\.)?field_overrides",
            region,
        )
        or re.search(r"composed\.field_overrides", region)
    )
    if not applies_raw:
        fails.append(
            "expandSimpleSetupDepth compose region does not read composed.field_overrides"
        )

    applies_setup = bool(
        re.search(
            r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*overrides\s*\}",
            region,
        )
    )
    if not applies_setup:
        # looser
        if "applyRandomizedSetup" in region and "overrides" in region:
            applies_setup = bool(
                re.search(r"applyRandomizedSetup\s*\([^)]*overrides", region)
            )
        if not applies_setup:
            fails.append(
                "expandSimpleSetupDepth compose region does not apply overrides "
                "via applyRandomizedSetup({ fields: overrides })"
            )

    # Guards that would fix the bug in the compose-apply region
    guard_patterns = [
        r"SIMPLE_INTENT_OVERRIDE_KEYS\.has\s*\(",
        r"SIMPLE_RANDOM_FIELD_ORDER\.includes\s*\(",
        r"filterIntentOverridesForMode\s*\(",
        # strip loop before apply, similar to stash path
        r"if\s*\(\s*SIMPLE_INTENT_OVERRIDE_KEYS",
        r"for\s*\(\s*const\s+\[[^\]]+\]\s+of\s+Object\.entries\s*\(\s*(?:overrides|raw)",
        r"userEdited|dirty|onlyEmpty|ifEmpty|skipSurface|preserveUser|depthOnly|depth_only",
    ]
    has_guard = any(re.search(p, region, flags=re.I) for p in guard_patterns)

    # Positive proof: applyRandomizedSetup with full overrides object and no strip
    unconditional = bool(
        re.search(
            r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*overrides\s*\}\s*\)",
            region,
        )
    )
    if not unconditional:
        unconditional = bool(
            re.search(
                r"field_overrides[\s\S]{0,400}applyRandomizedSetup\s*\(",
                region,
            )
        )

    if applies_raw and unconditional and not has_guard:
        fails.append(
            "expandSimpleSetupDepth compose re-entry applies full composed.field_overrides "
            "via applyRandomizedSetup with no SIMPLE_INTENT_OVERRIDE_KEYS / "
            "SIMPLE_RANDOM_FIELD_ORDER filter (post-pushSimpleToForm surface edits "
            "can be re-clobbered on Start when compose succeeds)"
        )
    elif has_guard and unconditional:
        # Fixed path filters compose overrides like stash — not a failure
        pass

    # Contrast: stash path in same function SHOULD filter (sanity that we look at right bug)
    stash_region = code
    m_compose = re.search(r"composeSetupIntent\s*\(\s*idea\s*\)", code)
    if m_compose:
        stash_region = code[: m_compose.start()]
    stash_strips = bool(
        re.search(r"SIMPLE_INTENT_OVERRIDE_KEYS\.has", stash_region)
        or re.search(r"SIMPLE_RANDOM_FIELD_ORDER\.includes", stash_region)
    )
    if not stash_strips and "_full_field_overrides" in stash_region:
        # Not required for this candidate; note only if stash also raw
        pass

    apply_fn = _fn_body(text, "function applyRandomizedSetup(", max_chars=2500)
    if not apply_fn:
        fails.append("applyRandomizedSetup missing")
    else:
        acode = _strip_line_comments(apply_fn)
        # Confirms setField overwrites without empty/user-edit skip for surface keys
        if "setField(" not in acode:
            fails.append("applyRandomizedSetup does not call setField")
        if re.search(
            r"if\s*\(\s*String\s*\(\s*setupForm.*value.*\)\.trim\(\)\s*\)\s*return",
            acode,
        ):
            pass  # empty-guard would mitigate

    return fails


def simulate_compose_reentry_clobber() -> list[str]:
    """Simulate Start expand after user surface edits when compose returns full overrides.

    Model (buggy product today):
      form = push_simple_to_form(user_simple_edits)
      depth = stash minus SIMPLE surface keys  # fixed path — surface preserved
      form = apply_all_keys(depth)
      compose_overrides = full field_overrides from network  # BUG: unfiltered
      form = apply_all_keys(compose_overrides)  # re-clobbers surface
      submitted = form

    Expectation when fixed: user surface edits win against compose overrides too.
    This sim fails (returns fail strings) while the bug model is used; when we
    detect product should preserve, the sim asserts preservation and reports
    fails if clobber occurs.
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
        "custom_style",
        "hair",
        "facial_features",
        "appearance",
        "starter_equipment",
        "player_sex",
        "death_rules",
        "leveling_system",
        "game_system",
        "system_style",
        "dice_checks_enabled",
        "proficiency_system",
        "skill_levels_enabled",
        "backstory_mode",
        "memory_policy",
        "race_magic_enabled",
    }

    # Stash from prior Simple randomize (mixed surface + depth)
    stashed_raw = {
        "player_name": "Kael Ashford",
        "difficulty": "hard",
        "magic_level": "rare",
        "tone": "grim hope",
        "quest_style": "local stakes",
    }
    # User edits after Randomize / before Start (pushed by pushSimpleToForm)
    user_simple = {
        "player_name": "User Edited Name",
        "difficulty": "easy",
        "magic_level": "rare",
    }
    # Compose on Start returns fresh full overrides including surface keys
    compose_overrides = {
        "player_name": "Compose Clobber Name",
        "difficulty": "nightmare",
        "tone": "bittersweet",
        "quest_style": "epic journey",
        "faction_pressure": "high",
    }

    form = dict(user_simple)

    # Fixed stash path: strip surface
    depth_only = {k: v for k, v in stashed_raw.items() if k not in simple_surface}
    for k, v in depth_only.items():
        form[k] = v

    # After fixed stash apply, surface must still match user
    for key in ("player_name", "difficulty"):
        if form.get(key) != user_simple.get(key):
            fails.append(
                f"sim-pre: after depth-only stash, {key}={form.get(key)!r} "
                f"lost user edit {user_simple.get(key)!r} (stash path broken)"
            )

    # BUG MODEL: apply raw compose overrides (mirrors current app.js lines)
    for k, v in compose_overrides.items():
        form[k] = v

    submitted = form
    clobbered = []
    for key in ("player_name", "difficulty"):
        if submitted.get(key) != user_simple.get(key):
            if submitted.get(key) == compose_overrides.get(key):
                clobbered.append(key)
                fails.append(
                    f"sim: Start submitted {key}={submitted.get(key)!r} "
                    f"(compose override) overwrote user edit {user_simple.get(key)!r} "
                    f"after stash guard had preserved it"
                )
            else:
                fails.append(
                    f"sim: Start submitted {key}={submitted.get(key)!r} "
                    f"did not preserve user edit {user_simple.get(key)!r}"
                )

    # Advanced-depth from compose is fine
    if submitted.get("faction_pressure") != compose_overrides.get("faction_pressure"):
        fails.append("sim: advanced-depth faction_pressure from compose was not applied")

    if not clobbered and not fails:
        # If we reach here under bug model, something wrong with sim
        fails.append("sim: expected compose surface clobber did not occur in bug model")

    return fails


def simulate_fixed_compose_filter() -> list[str]:
    """Sanity: if compose overrides were filtered like stash, surface edits survive.

    Not used as a product pass/fail by itself — documents intended fix semantics.
    Returns fails only if the fixed model incorrectly drops advanced keys.
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
    user_simple = {"player_name": "User Edited Name", "difficulty": "easy"}
    compose_overrides = {
        "player_name": "Compose Clobber Name",
        "difficulty": "nightmare",
        "tone": "bittersweet",
        "quest_style": "epic journey",
    }
    form = dict(user_simple)
    depth = {k: v for k, v in compose_overrides.items() if k not in simple_surface}
    for k, v in depth.items():
        form[k] = v
    for key in ("player_name", "difficulty"):
        if form.get(key) != user_simple.get(key):
            fails.append(f"fixed-model: surface {key} not preserved")
    if form.get("tone") != "bittersweet":
        fails.append("fixed-model: advanced tone not applied")
    return fails


def main() -> int:
    if not APP_JS.is_file():
        print(f"FAIL: missing {APP_JS}")
        return 1

    text = APP_JS.read_text(encoding="utf-8")
    fails = check_static(text)

    # Simulation encodes the buggy compose path; it always reports clobber fails
    # under the current product model. We only treat sim fails as evidence when
    # static analysis also found the unguarded apply (proves code matches model).
    sim_fails = simulate_compose_reentry_clobber()
    fixed_fails = simulate_fixed_compose_filter()
    if fixed_fails:
        fails.extend([f"harness-internal: {f}" for f in fixed_fails])

    static_found_bug = any("compose re-entry applies full" in f for f in fails)
    if static_found_bug:
        fails.extend(sim_fails)
    else:
        # Product guarded: sim under fixed semantics should preserve surface.
        # Re-run preservation check against filtered model (already in fixed_fails).
        # If static says fixed but we still see unfiltered apply patterns, check_static
        # would have failed; nothing more to add.
        pass

    if fails:
        print("FAIL: Simple Start compose re-entry can re-clobber surface edits")
        for f in fails:
            print(f" - {f}")
        print(
            "\nEvidence summary: expandSimpleSetupDepth strips Simple-surface keys "
            "from _full_field_overrides, then on idea re-compose applies "
            "composed.field_overrides via applyRandomizedSetup without the same "
            "SIMPLE_INTENT_OVERRIDE_KEYS / SIMPLE_RANDOM_FIELD_ORDER filter; "
            "simulation shows player_name/difficulty user edits lose to compose."
        )
        return 1

    print(
        "OK: Simple Start compose re-entry does not re-clobber post-edit surface keys"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
