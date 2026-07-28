"""Themed arrival locations + heavens prison (blank map / movement lock)."""

from __future__ import annotations

from app.setup_composer import (
    LOCATION_SEEDS_BY_THEME,
    detect_location_theme,
    ensure_isekai_start_location,
    location_special_flags_for,
    pick_isekai_arrival_location,
)


def test_theme_detection_keywords():
    assert detect_location_theme(world_style="neon cyberpunk megacity") == "cyberpunk"
    assert detect_location_theme(genre="steampunk airship adventure") == "steampunk"
    assert detect_location_theme(idea="post-apoc wasteland scrap") == "wasteland"
    assert detect_location_theme(world_style="the heavens afterlife") == "celestial"
    assert detect_location_theme(world_style="orbital station sci-fi") == "space"
    assert detect_location_theme(world_style="frontier dark fantasy") == "fantasy"


def test_pick_respects_theme_pool():
    cyber = pick_isekai_arrival_location(world_style="cyberpunk neon sprawl", seed=42)
    assert cyber in LOCATION_SEEDS_BY_THEME["cyberpunk"]

    steam = pick_isekai_arrival_location(genre="steampunk clockwork", seed=7)
    assert steam in LOCATION_SEEDS_BY_THEME["steampunk"]

    waste = pick_isekai_arrival_location(idea="wasteland fallout ruins", seed=99)
    assert waste in LOCATION_SEEDS_BY_THEME["wasteland"]

    heaven = pick_isekai_arrival_location(world_style="celestial heavens paradise", seed=3)
    assert heaven in LOCATION_SEEDS_BY_THEME["celestial"]


def test_heavens_flags_blank_and_locked():
    flags = location_special_flags_for("Prison of Light", theme="celestial")
    assert flags["map_blank"] is True
    assert flags["movement_locked"] is True
    assert flags["reason"] == "celestial_confinement"

    # Name alone can trigger even if theme not set
    flags2 = location_special_flags_for("Empty Empyrean", theme="fantasy")
    assert flags2["map_blank"] is True
    assert flags2["movement_locked"] is True

    normal = location_special_flags_for("Mosswake Gate", theme="fantasy")
    assert normal["map_blank"] is False
    assert normal["movement_locked"] is False


def test_ensure_isekai_replaces_earth_with_theme():
    loc, changed = ensure_isekai_start_location(
        "Seoul warehouse night shift",
        backstory_mode="transmigrated",
        idea="cyberpunk isekai",
        world_style="neon cyberpunk",
        character_backstory="I woke in another world after dying.",
    )
    assert changed is True
    assert loc in LOCATION_SEEDS_BY_THEME["cyberpunk"]


def test_each_theme_pool_nonempty():
    for tid, pool in LOCATION_SEEDS_BY_THEME.items():
        assert len(pool) >= 10, f"{tid} pool too small: {len(pool)}"
        assert all(isinstance(n, str) and n.strip() for n in pool)
