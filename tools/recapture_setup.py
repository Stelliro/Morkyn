from pathlib import Path
from playwright.sync_api import sync_playwright

MEDIA = Path(__file__).resolve().parent.parent / "Media"
BASE = "http://127.0.0.1:8765"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 960}).new_page()
        page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1000)
        if page.locator("#newGameButton").count():
            page.locator("#newGameButton").click()
            page.wait_for_timeout(900)
        page.screenshot(path=str(MEDIA / "ui-setup.png"), full_page=False)
        page.locator('button[data-setup-step="1"]').click(force=True)
        page.wait_for_timeout(450)
        page.screenshot(path=str(MEDIA / "ui-setup-world.png"), full_page=False)
        page.locator("#setupModelButton").click()
        page.wait_for_timeout(700)
        page.screenshot(path=str(MEDIA / "ui-model-settings.png"), full_page=False)
        browser.close()
    for name in ("ui-setup.png", "ui-setup-world.png", "ui-model-settings.png"):
        path = MEDIA / name
        print(name, path.stat().st_size)


if __name__ == "__main__":
    main()
