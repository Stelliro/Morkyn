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

Writes data/playtest_reports/setup_presets_<stamp>/<run>.json plus summary.json.
Requires the system Python (llama_cpp + playwright). Stops nothing it did not start.
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


def start_server(model: str) -> tuple[subprocess.Popen, str, str]:
    port = free_port()
    data_dir = tempfile.mkdtemp(prefix="morkyn_presets_")
    env = {
        **os.environ,
        "AI_RPG_DATA_DIR": data_dir,
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
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    stamp = time.strftime("%Y%m%d-%H%M%S")
    OUT_DIR = str(ROOT / "data" / "playtest_reports" / f"setup_presets_{stamp}")
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
            proc, base, data_dir = start_server(model)
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
