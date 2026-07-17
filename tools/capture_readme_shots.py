"""Capture Mørkyn UI into uniquely named Media files for README."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "Media"
BASE = "http://127.0.0.1:8765"


def shot(page, name: str) -> None:
    path = MEDIA / name
    page.screenshot(path=str(path), full_page=False)
    print(f"wrote {name} ({path.stat().st_size} bytes)")


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 960}).new_page()
        page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1200)

        # Prefer setup if visible; otherwise open New
        if page.locator("#gameView:not(.hidden)").count():
            # Capture play first while game is loaded
            page.wait_for_timeout(800)
            shot(page, "screen-play.png")
            page.locator('#indexTabs button[data-tab="model"]').click()
            page.wait_for_timeout(600)
            shot(page, "screen-play-model.png")
            page.locator("#compactModeButton").click()
            page.wait_for_timeout(400)
            shot(page, "screen-play-compact.png")
            # Return to setup for setup shots
            page.locator("#newGameButton").click()
            page.wait_for_timeout(900)

        page.wait_for_selector("#setupView:not(.hidden), #setupForm", timeout=10000)
        shot(page, "screen-setup.png")
        page.locator('button[data-setup-step="1"]').click(force=True)
        page.wait_for_timeout(450)
        shot(page, "screen-setup-world.png")
        page.locator("#setupModelButton").click()
        page.wait_for_timeout(700)
        shot(page, "screen-model-settings.png")
        browser.close()

    for path in sorted(MEDIA.glob("screen-*.png")):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
