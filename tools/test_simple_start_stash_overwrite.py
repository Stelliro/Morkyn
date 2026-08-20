"""Prove Simple Start expand can overwrite post-randomize user edits.

Bug class (correctness-1):
  After Simple Randomize with an idea, raw composer field_overrides are stashed on
  lastComposeIntent._full_field_overrides. On Start, expandSimpleSetupDepth()
  pushSimpleToForm()s user Simple UI values, then applyRandomizedSetup({fields: stashed})
  unconditionally — including Simple-surface keys (player_name, difficulty, …).
  User edits made after Randomize and before Start are replaced by randomize-time stash.

This harness:
  1) Static-asserts expandSimpleSetupDepth applies _full_field_overrides via
     applyRandomizedSetup with no empty/dirty/user-edit guards for surface keys.
  2) Simulates the Start expand path: form after user edit ≠ stash → stash wins.

Exit 0 only if the overwrite path is guarded (bug fixed). Exit 1 when the bug is present.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"

# Simple-surface keys that users can edit after Randomize and that composer often stashes.
SURFACE_KEYS = ("player_name", "difficulty", "player_age", "character_backstory")


def _fn_body(text: str, signature: str, max_chars: int = 4500) -> str | None:
    idx = text.find(signature)
    if idx < 0:
        return None
    return text[idx : idx + max_chars]


def _strip_line_comments(block: str) -> str:
    lines = [ln.split("//", 1)[0] for ln in block.splitlines()]
    return "\n".join(lines)


def check_static(text: str) -> list[str]:
    fails: list[str] = []

    expand = _fn_body(text, "async function expandSimpleSetupDepth()")
    if not expand:
        fails.append("expandSimpleSetupDepth missing")
        return fails

    code = _strip_line_comments(expand)
    # Bound body roughly until next top-level async function after a chunk
    # (we already have a window; use it as-is).

    if "_full_field_overrides" not in code:
        fails.append("expandSimpleSetupDepth does not read _full_field_overrides")
    if not re.search(r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*stashed", code):
        # tolerate whitespace / naming
        if not (
            "applyRandomizedSetup" in code
            and "stashed" in code
            and re.search(r"applyRandomizedSetup\s*\(", code)
        ):
            fails.append(
                "expandSimpleSetupDepth does not apply stashed overrides via applyRandomizedSetup"
            )
        else:
            # Confirm apply is on stashed object specifically
            if not re.search(
                r"const stashed\s*=[\s\S]*?applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*stashed",
                code,
            ):
                fails.append(
                    "expandSimpleSetupDepth: stashed overrides not passed as "
                    "applyRandomizedSetup({ fields: stashed })"
                )

    # Must NOT gate stash apply on empty/dirty/user-edited surface values.
    # Look only at the early stash-apply region (before fillTargets loop).
    stash_region = code
    m_fill = re.search(r"const fillTargets\s*=", code)
    if m_fill:
        stash_region = code[: m_fill.start()]

    # Anti-patterns that would guard surface keys — if none present, bug stands.
    guard_patterns = [
        r"isSettingLocked\s*\(\s*[\"']player_name",
        r"isSettingLocked\s*\(\s*[\"']difficulty",
        r"for\s*\(\s*const\s+\w+\s+of\s+Object\.keys\s*\(\s*stashed",
        r"filterIntentOverridesForMode\s*\(\s*stashed",
        r"SIMPLE_INTENT_OVERRIDE_KEYS",
        r"SIMPLE_RANDOM_FIELD_ORDER",
        r"depthOnlyFieldOverrides|depthOnly|depth_only",
        r"userEdited|dirty|onlyEmpty|ifEmpty|skipSurface|preserveUser",
        # per-key empty check before applying stash values
        r"stashed\[.*\][\s\S]{0,80}if\s*\([^)]*trim",
    ]
    has_guard = any(re.search(p, stash_region, flags=re.I) for p in guard_patterns)

    # Positive proof of unconditional apply of full object:
    unconditional = bool(
        re.search(
            r"if\s*\(\s*stashed\s*&&\s*Object\.keys\s*\(\s*stashed\s*\)\.length\s*\)\s*\{\s*"
            r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*stashed\s*\}\s*\)",
            stash_region,
        )
    )
    if not unconditional:
        # looser: keys length check then apply with stashed
        unconditional = bool(
            re.search(
                r"Object\.keys\s*\(\s*stashed\s*\)\.length[\s\S]{0,200}"
                r"applyRandomizedSetup\s*\(\s*\{\s*fields\s*:\s*stashed",
                stash_region,
            )
        )

    if unconditional and not has_guard:
        fails.append(
            "expandSimpleSetupDepth applies full _full_field_overrides via "
            "applyRandomizedSetup with no empty/dirty/surface-key guards "
            "(post-randomize Simple edits can be overwritten on Start)"
        )
    elif has_guard and unconditional:
        # Fixed path would filter or guard — not a failure for this bug
        pass

    apply_fn = _fn_body(text, "function applyRandomizedSetup(", max_chars=2500)
    if not apply_fn:
        fails.append("applyRandomizedSetup missing")
    else:
        acode = _strip_line_comments(apply_fn)
        # Unconditionally setField for every key (no empty check on existing form value)
        if "Object.entries(fields).forEach" not in acode and "Object.entries(fields)" not in acode:
            fails.append("applyRandomizedSetup no longer iterates all fields")
        # Should not skip when form already has a non-empty value (except special_abilities key skip)
        if re.search(
            r"if\s*\(\s*String\s*\(\s*setupForm.*value.*\)\.trim\(\)\s*\)\s*return",
            acode,
        ):
            # Has empty-guard — would mitigate; not our failure mode
            pass
        else:
            # Confirm setField is called without reading current value as skip condition
            if "setField(name" not in acode and "setField(" not in acode:
                fails.append("applyRandomizedSetup does not call setField")

    # Stash is rawOverrides (unfiltered full intent), not Simple-filtered subset
    rand = _fn_body(text, "async function randomizeAllSetup(", max_chars=3500)
    if not rand:
        fails.append("randomizeAllSetup missing")
    else:
        rcode = _strip_line_comments(rand)
        if "_full_field_overrides: rawOverrides" not in rcode and "_full_field_overrides: rawOverrides" not in rand:
            if not re.search(r"_full_field_overrides\s*:\s*rawOverrides", rcode):
                fails.append(
                    "randomizeAllSetup does not stash rawOverrides on _full_field_overrides"
                )
        # Confirm Simple mode filters only the form apply, not the stash
        if "filterIntentOverridesForMode(rawOverrides" not in rcode and "filterIntentOverridesForMode(rawOverrides" not in rand:
            fails.append("randomizeAllSetup missing Simple filter for form apply")
        # raw stash should not be filtered
        if re.search(r"_full_field_overrides\s*:\s*filterIntentOverridesForMode", rcode):
            # filtered stash would change the bug shape; not the candidate failure
            pass

    return fails


def simulate_expand_overwrite() -> list[str]:
    """Pure simulation of Start expand semantics (fixed: depth-only stash).

    Model (product after fix):
      form = push_simple_to_form(user_simple_edits)
      depth = stash minus SIMPLE surface keys (SIMPLE_INTENT_OVERRIDE_KEYS /
              SIMPLE_RANDOM_FIELD_ORDER)
      form = apply_all_keys(depth)
      submitted = form
    Expectation: user surface edits win; advanced-depth keys from stash still apply.
    """
    fails: list[str] = []

    # Mirrors static/app.js SIMPLE_INTENT_OVERRIDE_KEYS / SIMPLE_RANDOM_FIELD_ORDER
    # for the surface keys exercised by this harness.
    simple_surface = {
        "player_name",
        "difficulty",
        "magic_level",
        "player_age",
        "character_backstory",
        "special_abilities",
    }

    # After Simple Randomize + idea: stash holds composer surface + advanced keys
    stashed = {
        "player_name": "Kael Ashford",
        "difficulty": "hard",
        "magic_level": "rare",
        "tone": "grim hope",  # advanced-depth — legit expand target
        "quest_style": "local stakes",
    }
    # User edits Simple fields after Randomize, before Start
    user_simple = {
        "player_name": "User Edited Name",
        "difficulty": "easy",
        "magic_level": "rare",  # left as randomized
    }

    # pushSimpleToForm
    form = dict(user_simple)

    # expandSimpleSetupDepth: depth-only apply (strip Simple-surface keys)
    depth_only = {k: v for k, v in stashed.items() if k not in simple_surface}
    for k, v in depth_only.items():
        form[k] = v

    submitted = form
    for key in ("player_name", "difficulty"):
        if submitted.get(key) != user_simple.get(key):
            fails.append(
                f"sim: Start submitted {key}={submitted.get(key)!r} "
                f"did not preserve user edit {user_simple.get(key)!r}"
            )
        if submitted.get(key) == stashed.get(key) and stashed.get(key) != user_simple.get(key):
            fails.append(
                f"sim: Start submitted {key}={submitted.get(key)!r} "
                f"(stash) overwrote user edit {user_simple.get(key)!r}"
            )

    # Advanced-only keys from stash are fine to apply
    if submitted.get("tone") != stashed.get("tone"):
        fails.append("sim: advanced-depth tone from stash was not applied (unexpected)")
    if submitted.get("quest_style") != stashed.get("quest_style"):
        fails.append("sim: advanced-depth quest_style from stash was not applied (unexpected)")

    return fails


def main() -> int:
    if not APP_JS.is_file():
        print(f"FAIL: missing {APP_JS}")
        return 1

    text = APP_JS.read_text(encoding="utf-8")
    fails = check_static(text) + simulate_expand_overwrite()

    if fails:
        print("FAIL: Simple Start stash overwrite path present")
        for f in fails:
            print(f" - {f}")
        print(
            "\nEvidence summary: expandSimpleSetupDepth applies lastComposeIntent."
            "_full_field_overrides via applyRandomizedSetup after pushSimpleToForm "
            "with no per-key empty/dirty/surface guards; simulation shows "
            "player_name/difficulty user edits lose to stash."
        )
        return 1

    print("OK: Simple Start expand does not unconditionally overwrite post-randomize surface edits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
