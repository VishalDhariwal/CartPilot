import pytest
from datetime import datetime, date
from backend.agents.context_agent import (
    get_context,
    fetch_live_weather,
    get_upcoming_festivals,
    SEASON_MAP,
    DEFAULT_WEATHER_CITY
)


def test_meteorological_season_detection_all_months():
    """
    Verifies that the context agent maps all 12 calendar months to correct meteorological seasons.
    """
    expected = {
        1: "winter",
        2: "winter",
        3: "summer",
        4: "summer",
        5: "summer",
        6: "monsoon",
        7: "monsoon",
        8: "monsoon",
        9: "monsoon",
        10: "autumn_festive",
        11: "autumn_festive",
        12: "winter"
    }

    for month, exp_season in expected.items():
        test_dt = datetime(2026, month, 15, 12, 0, 0)
        ctx = get_context(city="Delhi", reference_dt=test_dt)
        assert ctx["season"] == exp_season, f"Month {month} should map to {exp_season}, got {ctx['season']}"
        assert len(ctx["season_label"]) > 0
        assert ctx["commercial_week"] >= 1 and ctx["commercial_week"] <= 53


def test_weather_fallback_graceful():
    """
    Verifies that weather fetching falls back gracefully to deterministic meteorological values
    without raising uncaught exceptions when no API key is configured.
    """
    weather = fetch_live_weather("Delhi")
    assert weather["city"] == "Delhi"
    assert "condition" in weather
    assert "temp_celsius" in weather
    assert "humidity_pct" in weather
    assert weather["temp_celsius"] > -20 and weather["temp_celsius"] < 60


def test_upcoming_festivals_detection():
    """
    Verifies that upcoming commercial festivals are discovered within the 30-day window.
    """
    # Test date near Diwali (Nov 1)
    diwali_eval_date = date(2026, 10, 20)
    festivals = get_upcoming_festivals(reference_date=diwali_eval_date, window_days=30)
    fest_names = [f["name"] for f in festivals]
    assert any("Diwali" in name for name in fest_names), f"Diwali should be detected within 30d of Oct 20. Found: {fest_names}"


def test_combined_category_boosts_monsoon():
    """
    Verifies that during Monsoon season, protective accessories (e.g. mobile-accessories)
    receive an elevated multiplier while sun protection (e.g. sunglasses) receives a penalty.
    """
    monsoon_dt = datetime(2026, 7, 15, 14, 0, 0)
    ctx = get_context(city="Delhi", reference_dt=monsoon_dt)

    boosts = ctx["category_boosts"]
    assert "mobile-accessories" in boosts
    assert boosts["mobile-accessories"]["multiplier"] >= 1.4
    assert "monsoon" in boosts["mobile-accessories"]["reason"].lower() or "rain" in boosts["mobile-accessories"]["reason"].lower()

    if "sunglasses" in boosts:
        assert boosts["sunglasses"]["multiplier"] <= 0.8
