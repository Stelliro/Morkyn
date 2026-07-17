from pathlib import Path
from playwright.sync_api import sync_playwright

MEDIA = Path(__file__).resolve().parent.parent / "Media"
BASE = "http://127.0.0.1:8765"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 960}).new_page()
        page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)

        if page.locator("#setupView:not(.hidden)").count():
            page.screenshot(path=str(MEDIA / "ui-setup.png"), full_page=False)
            page.locator('button[data-setup-step="1"]').click(force=True)
            page.wait_for_timeout(400)
            page.screenshot(path=str(MEDIA / "ui-setup-world.png"), full_page=False)
            page.locator("#setupModelButton").click()
            page.wait_for_timeout(600)
            page.screenshot(path=str(MEDIA / "ui-model-settings.png"), full_page=False)
            page.locator("#closeModelModal").click()
            print("captured setup views")

        if page.locator("#gameView:not(.hidden)").count():
            page.wait_for_timeout(1000)
            page.screenshot(path=str(MEDIA / "ui-play.png"), full_page=False)
            page.locator('#indexTabs button[data-tab="model"]').click()
            page.wait_for_timeout(700)
            page.screenshot(path=str(MEDIA / "ui-play-model.png"), full_page=False)
            page.locator("#compactModeButton").click()
            page.wait_for_timeout(500)
            page.screenshot(path=str(MEDIA / "ui-play-compact.png"), full_page=False)
            print("captured play views")
        else:
            print("game view not visible")

        browser.close()

    for path in sorted(MEDIA.glob("ui-*.png")):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
