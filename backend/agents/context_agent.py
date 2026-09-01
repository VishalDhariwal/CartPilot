"""
context_agent.py
================
Autonomous Context Signal Ingestion Engine for CartPilot.

Captures multi-layered environmental signals:
1. Meteorological Season (Summer, Monsoon, Festive Autumn, Winter)
2. Real-time Weather Integration (OpenWeatherMap API with robust local fallback)
3. Commercial ISO Calendar Weeks (e.g., Back-to-School, Festive Shopping Windows)
4. Indian Cultural & Festival Calendar (Diwali, Navratri, Holi, Eid, Raksha Bandhan, etc.)

Synthesizes these signals into actionable category-level boost multipliers and human-readable reasons.
"""

import os
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger("cartpilot.context_agent")

DEFAULT_WEATHER_CITY = "Delhi"

# ── 1. Meteorological Seasons Definition (India Focus) ─────────────────────────
SEASON_MAP = {
    1: {"season": "winter", "name": "Winter Peak", "temp_desc": "cold"},
    2: {"season": "winter", "name": "Late Winter / Spring Transition", "temp_desc": "cool"},
    3: {"season": "summer", "name": "Early Summer", "temp_desc": "warm"},
    4: {"season": "summer", "name": "Peak Summer", "temp_desc": "hot"},
    5: {"season": "summer", "name": "Late Summer Pre-Monsoon", "temp_desc": "very_hot"},
    6: {"season": "monsoon", "name": "Monsoon Arrival", "temp_desc": "humid_rainy"},
    7: {"season": "monsoon", "name": "Peak Monsoon", "temp_desc": "heavy_rain"},
    8: {"season": "monsoon", "name": "Active Monsoon", "temp_desc": "rainy"},
    9: {"season": "monsoon", "name": "Late Monsoon / Festive Transition", "temp_desc": "humid"},
    10: {"season": "autumn_festive", "name": "Festive Autumn (Navratri/Dussehra/Diwali)", "temp_desc": "pleasant"},
    11: {"season": "autumn_festive", "name": "Pre-Winter Wedding & Festive Season", "temp_desc": "crisp"},
    12: {"season": "winter", "name": "Winter Peak / Year-End", "temp_desc": "cold"}
}

# ── 2. Indian Commercial & Cultural Festival Calendar ─────────────────────────
# Approximate/Solar dates mapped for key annual e-commerce demand drivers
FESTIVAL_CALENDAR = [
    {"name": "Republic Day Mega Sale", "month": 1, "day": 26, "duration_days": 5, "categories": ["smartphones", "laptops", "mens-shirts", "furniture"]},
    {"name": "Holi Festive Shopping", "month": 3, "day": 15, "duration_days": 7, "categories": ["skin-care", "beauty", "mens-shirts", "groceries"]},
    {"name": "Eid al-Fitr Celebrations", "month": 4, "day": 10, "duration_days": 7, "categories": ["fragrances", "beauty", "mens-shirts", "mens-watches", "groceries"]},
    {"name": "Back-to-School / College Rush", "month": 6, "day": 25, "duration_days": 20, "categories": ["laptops", "tablets", "mobile-accessories", "sports-accessories"]},
    {"name": "Independence Day Freedom Sale", "month": 8, "day": 15, "duration_days": 6, "categories": ["smartphones", "laptops", "mens-shirts", "furniture", "home-decoration"]},
    {"name": "Raksha Bandhan Gifting", "month": 8, "day": 28, "duration_days": 7, "categories": ["fragrances", "beauty", "mens-watches", "skin-care", "groceries"]},
    {"name": "Onam Festive Season", "month": 9, "day": 5, "duration_days": 10, "categories": ["mens-shirts", "home-decoration", "kitchen-accessories", "groceries"]},
    {"name": "Navratri & Durga Puja", "month": 10, "day": 10, "duration_days": 10, "categories": ["mens-shirts", "beauty", "fragrances", "home-decoration", "skin-care"]},
    {"name": "Diwali & Dhanteras Festive Window", "month": 11, "day": 1, "duration_days": 12, "categories": ["home-decoration", "kitchen-accessories", "smartphones", "laptops", "fragrances", "beauty", "mens-watches"]},
    {"name": "Winter Wedding Season", "month": 11, "day": 25, "duration_days": 25, "categories": ["beauty", "fragrances", "mens-shirts", "mens-watches", "skin-care"]},
    {"name": "Christmas & New Year Clearance", "month": 12, "day": 25, "duration_days": 8, "categories": ["fragrances", "skin-care", "home-decoration", "smartphones"]}
]

# ── 3. Base Seasonal Category Affinity Rules ──────────────────────────────────
BASE_SEASONAL_CATEGORY_BOOSTS = {
    "monsoon": {
        "mobile-accessories": {"mul": 1.6, "reason": "Monsoon: high demand for waterproof pouches, rugged phone cases & chargers"},
        "sports-accessories": {"mul": 1.4, "reason": "Monsoon: outdoor sports gear and protective rain accessories active"},
        "skin-care": {"mul": 1.35, "reason": "Monsoon: humidity creates elevated demand for non-greasy skincare & facewash"},
        "kitchen-accessories": {"mul": 1.25, "reason": "Monsoon: indoor cooking & tea/snack appliances see elevated lift"},
        "sunglasses": {"mul": 0.5, "reason": "Monsoon: overcast/rainy weather reduces sun protection urgency"},
        "furniture": {"mul": 0.8, "reason": "Monsoon: major home moves and outdoor furniture sales slow down"}
    },
    "summer": {
        "sunglasses": {"mul": 1.8, "reason": "Peak Summer: high UV index drives strong demand for protective eyewear"},
        "skin-care": {"mul": 1.6, "reason": "Summer: sunscreens, refreshing face mists and lightweight hydration spike"},
        "fragrances": {"mul": 1.4, "reason": "Summer: fresh citrus & aquatic fragrances experience seasonal surge"},
        "mens-shirts": {"mul": 1.3, "reason": "Summer: breathable casual cotton & linen wear prioritized"},
        "sports-accessories": {"mul": 1.3, "reason": "Summer outdoor sports and fitness demand elevated"},
        "groceries": {"mul": 1.25, "reason": "Summer: hydration, beverages & summer essentials elevated"}
    },
    "winter": {
        "skin-care": {"mul": 1.75, "reason": "Winter: cold dry air drives intensive moisturizing creams & lip balms"},
        "home-decoration": {"mul": 1.4, "reason": "Winter: cozy indoor home decor, ambient lighting & warm living spaces"},
        "kitchen-accessories": {"mul": 1.35, "reason": "Winter: hot beverages, electric kettles and comfort cooking appliances"},
        "fragrances": {"mul": 1.3, "reason": "Winter: warm, woody, and gourmand perfumes trend higher"},
        "sunglasses": {"mul": 0.6, "reason": "Winter: reduced peak sunlight and lower outdoor sun-wear urgency"}
    },
    "autumn_festive": {
        "home-decoration": {"mul": 1.8, "reason": "Festive Season: pre-Diwali deep cleaning & festive home revamp"},
        "mens-shirts": {"mul": 1.6, "reason": "Festive Season: festive ethnic & formal shirts in peak demand"},
        "beauty": {"mul": 1.65, "reason": "Festive Season: Diwali & wedding celebratory beauty & styling surge"},
        "fragrances": {"mul": 1.6, "reason": "Festive Gifting: premium luxury perfumes spike for festive gifting"},
        "smartphones": {"mul": 1.4, "reason": "Festive electronics refresh and flagship upgrades"},
        "laptops": {"mul": 1.35, "reason": "Festive mega sales driving personal tech purchases"}
    }
}


def fetch_live_weather(city: str = DEFAULT_WEATHER_CITY) -> Dict[str, Any]:
    """
    Fetches real-time weather from OpenWeatherMap API if API key is present.
    Falls back gracefully to deterministic meteorological baseline if missing or unreachable.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY") or os.getenv("OPENWEATHERMAP_API_KEY") or os.getenv("WEATHER_API_KEY")
    
    # Baseline fallback based on current date
    now = datetime.now()
    month = now.month
    season_info = SEASON_MAP.get(month, {"season": "monsoon", "name": "Monsoon Season", "temp_desc": "humid_rainy"})
    
    fallback_result = {
        "city": city,
        "condition": "rain" if season_info["season"] == "monsoon" else ("clear" if season_info["season"] == "summer" else "haze"),
        "description": f"Seasonal baseline for {season_info['name']} ({city})",
        "temp_celsius": 29.0 if season_info["season"] == "monsoon" else (36.0 if season_info["season"] == "summer" else 19.0),
        "humidity_pct": 82 if season_info["season"] == "monsoon" else (45 if season_info["season"] == "summer" else 68),
        "is_live_api": False,
        "source": "meteorological_fallback"
    }

    if not api_key:
        return fallback_result

    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric"
        }
        with httpx.Client(timeout=2.5) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                weather_main = data.get("weather", [{}])[0].get("main", "").lower()
                weather_desc = data.get("weather", [{}])[0].get("description", "").lower()
                temp = float(data.get("main", {}).get("temp", 28.0))
                humidity = int(data.get("main", {}).get("humidity", 60))

                condition = "rain" if any(w in weather_main or w in weather_desc for w in ["rain", "drizzle", "thunderstorm", "shower"]) else (
                    "cold" if temp < 18 else (
                        "hot" if temp > 34 else "clear"
                    )
                )

                return {
                    "city": city,
                    "condition": condition,
                    "description": weather_desc.title(),
                    "temp_celsius": round(temp, 1),
                    "humidity_pct": humidity,
                    "is_live_api": True,
                    "source": "openweathermap"
                }
    except Exception as e:
        logger.warning(f"Live weather API lookup failed ({e}), using seasonal fallback.")

    return fallback_result


def get_upcoming_festivals(reference_date: Optional[date] = None, window_days: int = 30) -> List[Dict[str, Any]]:
    """
    Identifies commercial and cultural festivals occurring within window_days.
    """
    if reference_date is None:
        reference_date = date.today()

    active_festivals = []
    current_year = reference_date.year

    for fest in FESTIVAL_CALENDAR:
        # Check this year and next year for wrap-around
        for year in [current_year, current_year + 1]:
            try:
                fest_date = date(year, fest["month"], fest["day"])
            except ValueError:
                continue

            delta = (fest_date - reference_date).days
            # Active if currently in festival window or upcoming within window_days
            if -fest["duration_days"] <= delta <= window_days:
                status = "ongoing" if delta <= 0 else "upcoming"
                active_festivals.append({
                    "name": fest["name"],
                    "date": fest_date.isoformat(),
                    "days_away": max(0, delta),
                    "status": status,
                    "categories": fest["categories"]
                })

    active_festivals.sort(key=lambda x: x["days_away"])
    return active_festivals


def get_context(city: str = DEFAULT_WEATHER_CITY, reference_dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Synthesizes meteorological, commercial week, live weather, and cultural festival signals
    into unified category boost recommendations and human-readable reasoning.
    """
    if reference_dt is None:
        reference_dt = datetime.now()

    ref_date = reference_dt.date()
    month = reference_dt.month
    iso_week = reference_dt.isocalendar()[1]

    season_meta = SEASON_MAP.get(month, {"season": "monsoon", "name": "Monsoon Season", "temp_desc": "humid_rainy"})
    current_season = season_meta["season"]
    weather_data = fetch_live_weather(city)

    upcoming_festivals = get_upcoming_festivals(ref_date, window_days=30)

    # ── Compute Combined Category Multipliers ─────────────────────────────────
    category_boosts: Dict[str, Dict[str, Any]] = {}

    # 1. Base Seasonal Multipliers
    base_boosts = BASE_SEASONAL_CATEGORY_BOOSTS.get(current_season, {})
    for cat, info in base_boosts.items():
        category_boosts[cat] = {
            "multiplier": float(info["mul"]),
            "reasons": [info["reason"]],
            "signals": ["season"]
        }

    # 2. Weather Condition Modifiers
    weather_cond = weather_data.get("condition", "")
    if weather_cond == "rain":
        # Rain elevation
        cat_rain_elevations = {
            "mobile-accessories": (1.25, "Live Weather: Active rainfall in region increases demand for protective gear"),
            "kitchen-accessories": (1.15, "Live Weather: Rainy weather elevates home cooking and hot beverage gadgets")
        }
        for cat, (mul, reason) in cat_rain_elevations.items():
            if cat in category_boosts:
                category_boosts[cat]["multiplier"] = round(category_boosts[cat]["multiplier"] * mul, 2)
                category_boosts[cat]["reasons"].append(reason)
                category_boosts[cat]["signals"].append("live_weather")
            else:
                category_boosts[cat] = {"multiplier": mul, "reasons": [reason], "signals": ["live_weather"]}

    elif weather_cond == "hot" or weather_data.get("temp_celsius", 25) > 35:
        if "sunglasses" in category_boosts:
            category_boosts["sunglasses"]["multiplier"] = max(category_boosts["sunglasses"]["multiplier"], 1.5)
            category_boosts["sunglasses"]["reasons"].append("Live Weather: High temperature and intense sunlight")
            category_boosts["sunglasses"]["signals"].append("live_weather")

    # 3. Cultural & Festival Pre-Shopping Elevators
    for fest in upcoming_festivals:
        days_away = fest["days_away"]
        # Proximity weight: Closer festivals have stronger lift
        fest_lift = 1.35 if days_away <= 7 else (1.25 if days_away <= 15 else 1.15)
        for cat in fest["categories"]:
            fest_reason = f"Festive Lift: {fest['name']} ({days_away} days away) driving category demand"
            if cat in category_boosts:
                # Compound with dampening to prevent over-inflation
                category_boosts[cat]["multiplier"] = round(min(3.0, category_boosts[cat]["multiplier"] * fest_lift), 2)
                category_boosts[cat]["reasons"].append(fest_reason)
                category_boosts[cat]["signals"].append("festival")
            else:
                category_boosts[cat] = {
                    "multiplier": fest_lift,
                    "reasons": [fest_reason],
                    "signals": ["festival"]
                }

    # Format synthesized category dict (bounded between 0.2x and 3.0x)
    formatted_boosts = {}
    for cat, data in category_boosts.items():
        bounded_mul = round(max(0.2, min(3.0, data["multiplier"])), 2)
        combined_reason = " | ".join(data["reasons"])
        formatted_boosts[cat] = {
            "multiplier": bounded_mul,
            "reason": combined_reason,
            "signals": list(set(data["signals"]))
        }

    return {
        "timestamp": reference_dt.isoformat() + "Z",
        "season": current_season,
        "season_label": season_meta["name"],
        "commercial_week": iso_week,
        "weather": weather_data,
        "upcoming_festivals": upcoming_festivals,
        "category_boosts": formatted_boosts
    }
