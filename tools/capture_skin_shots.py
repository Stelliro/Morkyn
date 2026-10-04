"""Screenshot every main surface of the UI so a skin change can be checked by eye.

Run against a server that is NOT using your real save:

    AI_RPG_DB=/tmp/shots.db python -m uvicorn app.main:app --port 8765
    python tools/capture_skin_shots.py [out_dir] [--themes] [--import-debug-save]

What it writes (into out_dir, default data/ui-shots, which is gitignored):

    menu-<w>x<h>.png          main menu
    menu-<theme>.png          main menu in every theme (with --themes)
    setup-<w>x<h>.png         New game, Simple
    setup-model.png           LLM settings modal over setup
    play-<w>x<h>.png          play view (needs a world: pass --import-debug-save)
    play-drawer.png           play view with the Menu drawer open
    play-tools.png            the Tools / quests tab
    play-scene.png            scene focus

The debug save is data/debug-save.json (tools/make_debug_save.py). Importing it
REPLACES the world in whatever database the server is using, which is why the
server above is pointed at a scratch file.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"
SIZES = [(1440, 960), (1280, 800)]
THEMES = ["dusk", "ember", "tide", "bloom", "ash"]


def wait_for_server(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/api/version", timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server on 8765 did not answer")


def import_debug_save() -> None:
    save = ROOT / "data" / "debug-save.json"
    if not save.exists():
        raise SystemExit("no data/debug-save.json; run tools/make_debug_save.py first")
    req = urllib.request.Request(
        BASE + "/api/import",
        data=save.read_bytes(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        print("import:", resp.status, json.loads(resp.read().decode("utf-8")).get("ok", "?"))


def shot(page, out: Path, name: str) -> None:
    page.screenshot(path=str(out / name), full_page=False)
    print("wrote", name)


def set_theme(page, theme: str) -> None:
    page.evaluate(
        """(t) => {
            if (t === 'dusk') document.documentElement.removeAttribute('data-theme');
            else document.documentElement.setAttribute('data-theme', t);
        }""",
        theme,
    )
    page.wait_for_timeout(150)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    out = Path(args[0]) if args else ROOT / "data" / "ui-shots"
    out.mkdir(parents=True, exist_ok=True)
    wait_for_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width, height in SIZES:
            context = browser.new_context(viewport={"width": width, "height": height})
            # The first-run setup tour dims the whole form; mark it seen.
            context.add_init_script("try { localStorage.setItem('morkyn-setup-tutorial-v11', '1'); } catch (e) {}")
            page = context.new_page()
            page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(800)
            tag = f"{width}x{height}"

            if page.locator("#mainMenuView:not(.hidden)").count():
                shot(page, out, f"menu-{tag}.png")
                if "--themes" in flags and width == SIZES[0][0]:
                    for theme in THEMES:
                        set_theme(page, theme)
                        shot(page, out, f"menu-{theme}.png")
                    set_theme(page, "dusk")
                page.locator("#menuNewGame").click()
                page.wait_for_timeout(600)
                # Dismiss the first-run tutorial if it is up.
                for sel in ("#setupTourSkip", "#setupTutorialContinue"):
                    if page.locator(sel).count() and page.locator(sel).first.is_visible():
                        page.locator(sel).first.click()
                        page.wait_for_timeout(300)
                        break

            if page.locator("#setupView:not(.hidden)").count():
                shot(page, out, f"setup-{tag}.png")
                if width == SIZES[0][0]:
                    page.locator("#setupModelButton").click()
                    page.wait_for_timeout(500)
                    shot(page, out, "setup-model.png")
                    page.locator("#closeModelModal").click()
                    page.wait_for_timeout(200)
            page.context.close()

        if "--import-debug-save" in flags:
            import_debug_save()
            for width, height in SIZES:
                page = browser.new_context(viewport={"width": width, "height": height}).new_page()
                page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(1000)
                tag = f"{width}x{height}"
                if page.locator("#mainMenuView:not(.hidden)").count() and page.locator("#menuContinue:not([disabled])").count():
                    page.locator("#menuContinue").click()
                    page.wait_for_timeout(1200)
                if not page.locator("#gameView:not(.hidden)").count():
                    print("game view not visible at", tag)
                    shot(page, out, f"play-missing-{tag}.png")
                    page.context.close()
                    continue
                shot(page, out, f"play-{tag}.png")
                if width == SIZES[0][0]:
                    page.locator("#playMenuToggle").click()
                    page.wait_for_timeout(400)
                    shot(page, out, "play-drawer.png")
                    page.locator('[data-play-menu="tools"]').click()
                    page.wait_for_timeout(700)
                    shot(page, out, "play-tools.png")
                    page.locator("#playMenuToggle").click()
                    page.wait_for_timeout(300)
                    if page.locator("#playMenuDrawer:not(.hidden)").count():
                        page.locator('[data-play-menu="scene"]').click()
                        page.wait_for_timeout(600)
                        shot(page, out, "play-scene.png")
                page.context.close()
        browser.close()

    for path in sorted(out.glob("*.png")):
        print(f"  {path.name}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
