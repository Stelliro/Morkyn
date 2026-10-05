"""
Drive the New game page the way a player does: pick a preset, press Confirm
preset, wait for the Randomize walk to finish, and record what landed in every
setting, where each value came from (model or fallback), and what the browser
reported.

Runs (each in a fresh browser profile against its own scratch database):

  control_untouched   open New game, press nothing; the defaults Start would get
  control_fallback    Overpowered preset against a server whose model cannot load,
                      so every field comes from the offline fallbacks
  control_typed       Overpowered idea typed into the preset Idea box by hand
  preset:<id> x N     built-in presets, Overpowered and Cyberpunk always, the rest
                      drawn at random

Usage:
  python tools/playtest_setup_presets.py --model D:\\path\\Qwen3-8B-Q4_K_M.gguf [--random 3] [--seed 7] [--only op_mc,cyberpunk]
      [--out DIR] [--no-launcher-env]

The server runs with the player's launcher env (data/launcher_prefs.json, read
only, mapped the way Morkyn.ps1 maps it): narration pipeline, consolidation,
fast verification, DSL skip-verify, draft mode, flash attention, response caps
and context. Without it the harness tests the shipped defaults, a narration
path the player does not run (playtest #38). --no-launcher-env opts out.

Writes <temp>/morkyn_setup_presets_<stamp>/<run>.json plus summary.json, or
under --out. Never under data/. Every data store the server touches lives in
its own temp dir. Requires the system Python (llama_cpp + playwright). Stops
nothing it did not start.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

BUILTIN = [
    "op_mc", "fantasy", "adventurers", "cyberpunk", "iron_front", "court", "frontier", "depth",
    "isekai", "wuxia", "academy", "wasteland", "salvage", "gothic", "noir", "apocalypse", "hearth",
]

# Wraps fetch so every setup call is recorded with its request, response and timing.
FETCH_LOGGER = r"""
(() => {
  window.__setupLog = [];
  const real = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const watch = /\/api\/(randomize-setup|setup\/|compose-intent)/.test(url);
    const t0 = performance.now();
    const res = await real(input, init);
    if (watch) {
      let req = null, body = null;
      try { req = JSON.parse(init.body || "null"); } catch (_) { req = String(init.body || "").slice(0, 400); }
      try { body = await res.clone().json(); } catch (_) { body = null; }
      window.__setupLog.push({ url, status: res.status, ms: Math.round(performance.now() - t0), req, body });
    }
    return res;
  };
})();
"""

SNAPSHOT = r"""
() => {
  try { if (typeof setupUiMode !== "undefined" && setupUiMode === "simple") pushSimpleToForm(); } catch (e) {}
  const fd = new FormData(setupForm);
  const fields = {};
  (RANDOM_FIELD_ORDER || []).forEach((name) => {
    try { fields[name] = setupSnapshotValue(fd, name); } catch (e) { fields[name] = "<err " + e + ">"; }
  });
  return {
    fields,
    gear: (() => { try { return collectGearItems(); } catch (e) { return "<err " + e + ">"; } })(),
    abilities: (() => { try { return collectAbilities(); } catch (e) { return "<err " + e + ">"; } })(),
    status: document.querySelector("#setupRandomizeStatus")?.textContent || "",
    idea: (() => { try { return setupRandomizeIdea(); } catch (e) { return ""; } })(),
    ui_mode: typeof setupUiMode !== "undefined" ? setupUiMode : "",
    log: window.__setupLog || [],
  };
}
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def isolated_data_env(data_dir: str) -> dict[str, str]:
    """Every path setting the server reads, pointed inside ``data_dir``."""
    root = Path(data_dir)
    (root / "campaign_slots").mkdir(parents=True, exist_ok=True)
    return {
        "AI_RPG_DB": str(root / "world.db"),
        "AI_RPG_CAMPAIGN_SLOTS": str(root / "campaign_slots"),
        "AI_RPG_HISTORY_SUMMARY": str(root / "history_summaries.jsonl"),
        "AI_RPG_SOURCE_INDEX": str(root / "source_index"),
        "AI_RPG_CONSOLIDATED_FACTS": str(root / "consolidated_facts.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(root / "model_traces"),
        # Playtest #38: these four defaulted to the live data/ files.
        "AI_RPG_IDEA_BANK": str(root / "idea_bank"),
        "AI_RPG_LAUNCHER_PREFS": str(root / "launcher_prefs.json"),
        "AI_RPG_SKILL_LIBRARY": str(root / "skill_library.json"),
        "AI_RPG_PACK_DIR": str(root / "packs"),
    }


# The player's launcher prefs. Read, never written.
LIVE_LAUNCHER_PREFS = ROOT / "data" / "launcher_prefs.json"


def read_launcher_prefs(path: Path | None = None) -> dict:
    """The player's launcher prefs (the file is saved by PowerShell with a BOM), or {}."""
    source = Path(path or LIVE_LAUNCHER_PREFS)
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _pref_int(value) -> int:
    text = str(value if value is not None else "").strip().lower()
    if not text or text == "auto":
        return 0
    try:
        number = int(float(text))
    except ValueError:
        return 0
    return number if number > 0 else 0


def launcher_env(prefs: dict) -> dict[str, str]:
    """The env Morkyn.ps1 exports from the launcher prefs (the turn pipeline's switches)."""
    on = lambda key, default=True: "1" if prefs.get(key, default) else "0"  # noqa: E731
    env = {
        "AI_RPG_DRAFT_MODE": str(prefs.get("draft_mode") or "dsl"),
        "AI_RPG_NARRATION_PIPELINE": on("narration_pipeline"),
        "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": on("narration_consolidate"),
        "AI_RPG_FAST_VERIFICATION": on("fast_verification"),
        "AI_RPG_DSL_SKIP_VERIFY": on("dsl_skip_verify", False),
        "AI_RPG_LLAMA_CPP_FLASH_ATTN": "True" if prefs.get("llama_cpp_flash_attn") else "False",
    }
    if prefs.get("llama_cpp_gpu_layers") is not None:
        env["AI_RPG_LLAMA_CPP_GPU_LAYERS"] = str(int(prefs.get("llama_cpp_gpu_layers")))
    for key, name in (
        ("llama_cpp_context", "AI_RPG_CONTEXT_TOKENS"),
        ("soft_response_tokens", "AI_RPG_MAX_RESPONSE_TOKENS"),
        ("hard_response_tokens", "AI_RPG_RESPONSE_HARD_CAP_TOKENS"),
    ):
        number = _pref_int(prefs.get(key))
        if number:
            env[name] = str(number)
    return env


def default_out_dir(stamp: str) -> str:
    """Reports go to the temp dir, never under the live data/ tree."""
    return str(Path(tempfile.gettempdir()) / f"morkyn_setup_presets_{stamp}")


def start_server(model: str, *, use_launcher_env: bool = True) -> tuple[subprocess.Popen, str, str]:
    port = free_port()
    data_dir = tempfile.mkdtemp(prefix="morkyn_presets_")
    # Mørkyn has no single data-dir setting: every store has its own variable,
    # and each one left unset defaults to the player's real files under data/.
    # An earlier version of this tool set a non-existent AI_RPG_DATA_DIR and
    # wrote into the live world.db and save folder.
    isolated = isolated_data_env(data_dir)
    prefs = read_launcher_prefs() if use_launcher_env else {}
    # The server reads (and Settings may save) a private copy, never the live file.
    Path(isolated["AI_RPG_LAUNCHER_PREFS"]).write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    base_env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("AI_RPG_CONTEXT_TOKENS", "AI_RPG_MAX_RESPONSE_TOKENS", "AI_RPG_RESPONSE_HARD_CAP_TOKENS")
        or not use_launcher_env
    }
    env = {
        **base_env,
        **(launcher_env(prefs) if use_launcher_env else {}),
        **isolated,
        "AI_RPG_MODEL_PROVIDER": "mle",
        "MLE_MODEL": model,
        "PYTHONIOENCODING": "utf-8",
    }
    log = open(Path(data_dir) / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/api/version", timeout=2)
            return proc, base, data_dir
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("server did not start; see " + data_dir)


def warm_model(base: str) -> dict:
    t0 = time.time()
    try:
        with urllib.request.urlopen(base + "/api/model-status", timeout=600) as r:
            out = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        out = {"ok": False, "error": str(exc)}
    out["_warm_seconds"] = round(time.time() - t0, 1)
    return out


def open_setup(page, base: str) -> None:
    page.goto(base + "/", wait_until="load")
    page.wait_for_timeout(2500)
    page.locator("#menuNewGame").click()
    page.wait_for_timeout(1500)
    for _ in range(3):
        for sel in ("#setupTourSkip", "#setupTutorialContinue"):
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.click()
                page.wait_for_timeout(300)
        skip = page.get_by_role("button", name="Skip")
        if skip.count() and skip.first.is_visible():
            skip.first.click()
            page.wait_for_timeout(300)


def wait_for_walk(page, timeout_s: int) -> float:
    """Wait for the form to go busy, then idle for 8 s straight."""
    t0 = time.time()
    seen_busy = False
    idle_since = None
    while time.time() - t0 < timeout_s:
        busy = page.evaluate("() => setupForm.getAttribute('aria-busy') === 'true'")
        if busy:
            seen_busy = True
            idle_since = None
        else:
            idle_since = idle_since or time.time()
            if (seen_busy and time.time() - idle_since > 8) or (not seen_busy and time.time() - t0 > 60):
                break
        page.wait_for_timeout(1000)
    return round(time.time() - t0, 1)


def run_one(pw, base: str, name: str, mode: str, preset: str, typed_idea: str, timeout_s: int) -> dict:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
    ctx.add_init_script(FETCH_LOGGER)
    page = ctx.new_page()
    errors: list[str] = []
    console: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}"[:400]) if m.type in ("error", "warning") else None)
    open_setup(page, base)
    result: dict = {"run": name, "mode": mode, "preset": preset}
    if mode != "untouched":
        # The presets card opens collapsed; a player clicks it open first.
        if not page.locator("#presetSelect").is_visible():
            page.locator("#setupPresetToggle").click()
            page.wait_for_timeout(400)
        page.select_option("#presetSelect", f"preset:{preset}")
        page.wait_for_timeout(600)
        if mode == "typed":
            box = page.locator("#presetSimpleIdea")
            box.fill("")
            box.type(typed_idea, delay=2)
            page.wait_for_timeout(300)
        result["idea_sent"] = page.evaluate("() => setupRandomizeIdea()")
        page.locator("#presetConfirmBtn").click()
        result["walk_seconds"] = wait_for_walk(page, timeout_s)
    snap = page.evaluate(SNAPSHOT)
    result.update(snap)
    # Start runs expandSimpleSetupDepth() before it posts the setup; Simple
    # Randomize leaves tone, tech, start location, custom skills and the like
    # to that pass. Run it here (without starting the game) and record what
    # Start would actually send.
    t1 = time.time()
    try:
        page.evaluate("async () => { if (typeof setupUiMode !== 'undefined' && setupUiMode === 'simple') await expandSimpleSetupDepth(); }")
        page.wait_for_timeout(1500)
        after = page.evaluate(SNAPSHOT)
        result["at_start"] = {k: after[k] for k in ("fields", "gear", "abilities", "status")}
        result["at_start"]["log"] = after["log"][len(snap["log"]):]
    except Exception as exc:  # noqa: BLE001
        result["at_start"] = {"error": str(exc)[:400]}
    result["expand_seconds"] = round(time.time() - t1, 1)
    result["page_errors"] = errors
    result["console"] = console[-60:]
    try:
        page.screenshot(path=str(Path(OUT_DIR) / f"{name}.png"), full_page=False)
    except Exception:
        pass
    ctx.close()
    browser.close()
    return result


def summarize(result: dict) -> dict:
    log = result.get("log") or []
    calls = [e for e in log if "randomize-setup" in e["url"]]
    fallback = [
        (e.get("req") or {}).get("group")
        for e in calls
        if isinstance(e.get("body"), dict) and e["body"].get("fallback_used")
    ]
    failed = [(e.get("req") or {}).get("group") for e in calls if e["status"] != 200]
    return {
        "run": result["run"],
        "walk_seconds": result.get("walk_seconds"),
        "randomize_calls": len(calls),
        "fallback_groups": fallback,
        "http_failures": failed,
        "page_errors": len(result.get("page_errors") or []),
        "status": result.get("status"),
    }


OUT_DIR = ""


def main() -> int:
    global OUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--random", type=int, default=3)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--skip-controls", action="store_true")
    ap.add_argument("--out", default="", help="report folder (default: the temp dir; never under data/)")
    ap.add_argument("--no-launcher-env", action="store_true", help="run the shipped defaults, not the player's launcher env")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    stamp = time.strftime("%Y%m%d-%H%M%S")
    OUT_DIR = args.out or default_out_dir(stamp)
    try:
        Path(OUT_DIR).resolve().relative_to((ROOT / "data").resolve())
        raise SystemExit("--out must not be under data/ (the player's live game)")
    except ValueError:
        pass
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    if args.only:
        presets = [p.strip() for p in args.only.split(",") if p.strip()]
    else:
        rest = [p for p in BUILTIN if p not in ("op_mc", "cyberpunk")]
        presets = ["op_mc", "cyberpunk", *rng.sample(rest, k=max(0, args.random))]
    op_mc_idea = (
        "Overpowered progression in any setting: start ordinary with one weak compounding seed power that "
        "snowballs toward late-game OP (rank F up through S/SS/SSS). Growth Math makes the climb calculable; "
        "passives allowed; more powers can unlock later. Normal difficulty; mythic progression tone; local "
        "stakes early; fair DM."
    )
    runs: list[tuple[str, str, str, str]] = []  # (name, mode, preset, server)
    if not args.skip_controls:
        runs += [
            ("control_untouched", "untouched", "", "model"),
            ("control_fallback", "preset", "op_mc", "dead"),
            ("control_typed", "typed", "op_mc", "model"),
        ]
    runs += [(f"preset_{p}", "preset", p, "model") for p in presets]
    summary = {"model": args.model, "out": OUT_DIR, "runs": []}
    print("writing to", OUT_DIR, flush=True)

    with sync_playwright() as pw:
        for server_kind in ("dead", "model"):
            todo = [r for r in runs if r[3] == server_kind]
            if not todo:
                continue
            model = args.model if server_kind == "model" else str(ROOT / "data" / "no-such-model.gguf")
            proc, base, data_dir = start_server(model, use_launcher_env=not args.no_launcher_env)
            try:
                summary[f"{server_kind}_server"] = {"base": base, "data_dir": data_dir, "status": warm_model(base)}
                print(server_kind, "server", base, summary[f"{server_kind}_server"]["status"].get("ok"), flush=True)
                for name, mode, preset, _ in todo:
                    t0 = time.time()
                    print(f"-> {name}", flush=True)
                    result = run_one(pw, base, name, mode, preset, op_mc_idea, args.timeout)
                    (Path(OUT_DIR) / f"{name}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
                    s = summarize(result)
                    summary["runs"].append(s)
                    print(f"   done in {round(time.time() - t0)}s: {json.dumps(s, ensure_ascii=False)[:400]}", flush=True)
                    (Path(OUT_DIR) / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except Exception:
                    proc.kill()
    print("summary:", Path(OUT_DIR) / "summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
