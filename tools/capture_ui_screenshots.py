"""Capture live Mørkyn UI screenshots into Media/."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "Media"
BASE = "http://127.0.0.1:8765"


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def try_start_playthrough() -> bool:
    """Start a playthrough so we can capture the game view (uses model fallback if needed)."""
    payload = {
        "player_name": "Ashen Courier",
        "player_public_name": "the Ashbound",
        "player_title": "Courier",
        "player_age": "27",
        "player_sex": "unspecified",
        "previous_life_age": "",
        "previous_life_sex": "",
        "backstory_mode": "known",
        "character_backstory": "A road courier who still carries old debts and a sealed letter.",
        "memory_policy": "known",
        "difficulty": "normal",
        "narration_detail": "rich",
        "world_style": "frontier dark fantasy",
        "custom_style": "",
        "start_location": "Mosswake Gate",
        "leveling_system": True,
        "game_system": False,
        "system_style": "subtle blue-window system",
        "special_ability_origin": "none",
        "special_ability": False,
        "special_ability_locked": False,
        "special_ability_name": "",
        "special_ability_description": "",
        "special_abilities": [],
        "skill_style": "standard",
        "skill_levels_enabled": True,
        "new_skill_frequency": "normal",
        "proficiency_system": True,
        "proficiency_access": "learned",
        "skill_growth_speed": "normal",
        "proficiency_growth_speed": "normal",
        "xp_growth_speed": "normal",
        "custom_skills": "",
    }
    try:
        post_json("/api/setup", payload)
        return True
    except Exception as exc:
        print("setup failed:", exc)
        return False


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    print("API version:", get_json("/api/version"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
        page = context.new_page()
        page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(800)

        # 1) Setup / character screen
        page.screenshot(path=str(MEDIA / "ui-setup.png"), full_page=False)
        print("wrote ui-setup.png")

        # 2) World step
        page.click('button[data-setup-step="1"]')
        page.wait_for_timeout(400)
        page.screenshot(path=str(MEDIA / "ui-setup-world.png"), full_page=False)
        print("wrote ui-setup-world.png")

        # 3) LLM settings modal
        page.locator("#setupModelButton").click()
        page.wait_for_timeout(700)
        page.screenshot(path=str(MEDIA / "ui-model-settings.png"), full_page=False)
        print("wrote ui-model-settings.png")
        # close modal
        page.locator("#closeModelModal").click()
        page.wait_for_timeout(300)

        browser.close()

    # Try to enter play view via API (may use fallback without a model)
    started = try_start_playthrough()
    print("playthrough started:", started)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
        page = context.new_page()
        page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)

        # If setup still showing but state is complete, refresh/load should show game
        # The SPA loads /api/state on boot
        page.wait_for_timeout(1000)
        game_hidden = page.locator("#gameView.hidden").count() > 0
        print("gameView hidden:", game_hidden)

        if not game_hidden:
            # Wait for latest output / history to paint after state load
            page.wait_for_timeout(1200)
            try:
                page.wait_for_function(
                    """() => {
                        const out = document.querySelector('#latestOutput');
                        const hist = document.querySelector('#history');
                        const outText = (out && out.textContent || '').trim();
                        const histText = (hist && hist.textContent || '').trim();
                        return outText.length > 20 || histText.length > 40;
                    }""",
                    timeout=10000,
                )
            except Exception as exc:
                print("wait for play content:", exc)
            page.screenshot(path=str(MEDIA / "ui-play.png"), full_page=False)
            print("wrote ui-play.png")

            # Model tab for context health / budget card
            page.click('#indexTabs button[data-tab="model"]')
            page.wait_for_timeout(700)
            page.screenshot(path=str(MEDIA / "ui-play-model.png"), full_page=False)
            print("wrote ui-play-model.png")

            # Compact mode
            page.click("#compactModeButton")
            page.wait_for_timeout(500)
            page.screenshot(path=str(MEDIA / "ui-play-compact.png"), full_page=False)
            print("wrote ui-play-compact.png")
        else:
            # Fallback: still capture whatever is visible as play shell after reload attempt
            page.screenshot(path=str(MEDIA / "ui-play.png"), full_page=False)
            print("game view not visible; wrote current page as ui-play.png")

        browser.close()

    print("done. Media contents:")
    for path in sorted(MEDIA.glob("*.png")):
        print(" ", path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
