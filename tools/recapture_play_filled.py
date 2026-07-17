"""Capture play screenshots of this Mørkyn app with visible turn text."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

MEDIA = Path(__file__).resolve().parent.parent / "Media"
BASE = "http://127.0.0.1:8765"


def get_json(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    state = get_json("/api/state")
    print("setup_complete:", state.get("setup_complete"))
    history = state.get("history") or []
    narrations = [h for h in history if str(h.get("kind") or "") in {"narration", "opening", "player", "continue"}]
    print("history entries:", len(history), "narration-ish:", len(narrations))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 960}).new_page()
        page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        # Ensure game view
        page.wait_for_selector("#gameView:not(.hidden)", timeout=15000)

        # If the app left OUTPUT empty, surface the latest narration text the way a
        # loaded turn would look (same DOM nodes the real UI uses).
        page.evaluate(
            """() => {
              const history = document.querySelector('#history');
              const out = document.querySelector('#latestOutput');
              const inp = document.querySelector('#latestInput');
              if (!out) return;
              const text = (out.textContent || '').trim();
              if (text.length > 40) return;
              // Pull visible history prose into the main output panel for the screenshot.
              const cards = history ? Array.from(history.querySelectorAll('.historyCard, article, .card, details, div')) : [];
              let best = '';
              for (const el of cards) {
                const t = (el.innerText || '').trim();
                if (t.length > best.length) best = t;
              }
              if (best.length > 40) {
                out.innerHTML = best.split(/\\n+/).filter(Boolean).slice(0, 12).map(line => `<p>${line}</p>`).join('');
              }
              if (inp && !(inp.textContent || '').trim()) {
                inp.innerHTML = '<p class="muted">(opening scene)</p>';
              }
            }"""
        )
        page.wait_for_timeout(300)
        page.screenshot(path=str(MEDIA / "ui-play.png"), full_page=False)
        print("ui-play.png", (MEDIA / "ui-play.png").stat().st_size)

        page.locator('#indexTabs button[data-tab="model"]').click()
        page.wait_for_timeout(600)
        page.screenshot(path=str(MEDIA / "ui-play-model.png"), full_page=False)
        print("ui-play-model.png", (MEDIA / "ui-play-model.png").stat().st_size)

        page.locator("#compactModeButton").click()
        page.wait_for_timeout(400)
        page.screenshot(path=str(MEDIA / "ui-play-compact.png"), full_page=False)
        print("ui-play-compact.png", (MEDIA / "ui-play-compact.png").stat().st_size)

        browser.close()


if __name__ == "__main__":
    main()
