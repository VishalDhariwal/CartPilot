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
import json
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
    Fetches real-time live meteorological observations:
    1. Primary: Open-Meteo free global weather API (no key required, high precision live data).
    2. Secondary: OpenWeatherMap (if API key is present in environment).
    3. Fallback: Seasonal baseline if machine is offline.
    """
    # 1. Check OpenWeatherMap if key is provided
    api_key = os.getenv("OPENWEATHER_API_KEY") or os.getenv("OPENWEATHERMAP_API_KEY") or os.getenv("WEATHER_API_KEY")
    if api_key:
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": city, "appid": api_key, "units": "metric"}
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
                        "source": "openweathermap",
                        "fetched_at": datetime.utcnow().isoformat() + "Z"
                    }
        except Exception as e:
            logger.warning(f"OpenWeatherMap lookup failed ({e}), trying Open-Meteo...")

    # 2. Open-Meteo Free Live Real-time API (No API key needed)
    try:
        CITY_COORDS = {
            "Delhi": (28.6139, 77.2090),
            "New Delhi": (28.6139, 77.2090),
            "Mumbai": (19.0760, 72.8777),
            "Bengaluru": (12.9716, 77.5946),
            "Kolkata": (22.5726, 88.3639),
            "Chennai": (13.0827, 80.2707),
        }
        lat, lon = CITY_COORDS.get(city, (28.6139, 77.2090))
        meteo_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code&timezone=auto"
        
        WMO_MAP = {
            0: ("Clear sky", "clear"),
            1: ("Mainly clear", "clear"),
            2: ("Partly cloudy", "clouds"),
            3: ("Overcast", "clouds"),
            45: ("Foggy", "fog"),
            48: ("Depositing rime fog", "fog"),
            51: ("Light drizzle", "rain"),
            53: ("Moderate drizzle", "rain"),
            55: ("Dense drizzle", "rain"),
            61: ("Slight rain", "rain"),
            63: ("Moderate rain", "rain"),
            65: ("Heavy rain", "rain"),
            80: ("Slight rain showers", "rain"),
            81: ("Moderate rain showers", "rain"),
            82: ("Violent rain showers", "rain"),
            95: ("Thunderstorm", "rain"),
            96: ("Thunderstorm with hail", "rain"),
            99: ("Heavy thunderstorm", "rain"),
        }

        with httpx.Client(timeout=3.5) as client:
            resp = client.get(meteo_url)
            if resp.status_code == 200:
                cur = resp.json().get("current", {})
                temp = round(float(cur.get("temperature_2m", 28.0)), 1)
                humidity = int(cur.get("relative_humidity_2m", 60))
                code = int(cur.get("weather_code", 0))
                desc, cond = WMO_MAP.get(code, ("Partly cloudy", "clouds"))

                if cond in ("clear", "clouds"):
                    if temp > 34:
                        cond = "hot"
                    elif temp < 18:
                        cond = "cold"

                return {
                    "city": city,
                    "condition": cond,
                    "description": desc,
                    "temp_celsius": temp,
                    "humidity_pct": humidity,
                    "is_live_api": True,
                    "source": "open-meteo-live",
                    "fetched_at": datetime.utcnow().isoformat() + "Z"
                }
    except Exception as e:
        logger.warning(f"Open-Meteo live weather lookup failed: {e}")

    # 3. Fallback to seasonal baseline if offline
    now = datetime.now()
    month = now.month
    season_info = SEASON_MAP.get(month, {"season": "monsoon", "name": "Monsoon Season", "temp_desc": "humid_rainy"})
    return {
        "city": city,
        "condition": "rain" if season_info["season"] == "monsoon" else ("clear" if season_info["season"] == "summer" else "haze"),
        "description": f"Seasonal baseline for {season_info['name']} ({city})",
        "temp_celsius": 29.0 if season_info["season"] == "monsoon" else (36.0 if season_info["season"] == "summer" else 19.0),
        "humidity_pct": 82 if season_info["season"] == "monsoon" else (45 if season_info["season"] == "summer" else 68),
        "is_live_api": False,
        "source": "meteorological_fallback",
        "fetched_at": datetime.utcnow().isoformat() + "Z"
    }


def match_catalog_categories_to_themes(
    merchant_categories: list[str],
    themes: list[str],
    min_similarity: float = 0.45
) -> list[dict]:
    """
    Dynamically maps a merchant's live distinct catalog categories to festival commercial themes.
    Uses exact token matching (1.0) + dense MiniLM embeddings with graceful semantic cutoff.
    """
    if not merchant_categories or not themes:
        return []

    try:
        from backend.recommendations.embedding_engine import get_model
        import numpy as np

        model = get_model()

        # 1. First pass: direct substring / token matches
        matched_dict = {}
        unmatched_cats = []
        for cat in merchant_categories:
            clean_cat = cat.lower().replace("-", " ")
            for theme in themes:
                clean_theme = theme.lower().replace("_", " ")
                if clean_theme in clean_cat or clean_cat in clean_theme:
                    matched_dict[cat] = {"category": cat, "similarity": 1.0, "matched_theme": theme}
                    break
            if cat not in matched_dict:
                unmatched_cats.append(cat)

        # 2. Second pass: dense semantic embedding matching for remaining categories
        if model is not None and unmatched_cats and themes:
            cat_labels = [c.replace("-", " ") for c in unmatched_cats]
            theme_labels = [t.replace("_", " ") for t in themes]

            cat_vecs = model.encode(cat_labels, convert_to_numpy=True, normalize_embeddings=True)
            theme_vecs = model.encode(theme_labels, convert_to_numpy=True, normalize_embeddings=True)

            sim_matrix = cat_vecs @ theme_vecs.T
            max_sim_indices = np.argmax(sim_matrix, axis=1)
            max_sim_scores = np.max(sim_matrix, axis=1)

            for idx, (sim, t_idx) in enumerate(zip(max_sim_scores, max_sim_indices)):
                if sim >= min_similarity:
                    matched_dict[unmatched_cats[idx]] = {
                        "category": unmatched_cats[idx],
                        "similarity": round(float(sim), 4),
                        "matched_theme": themes[t_idx]
                    }

        result = list(matched_dict.values())
        result.sort(key=lambda x: x["similarity"], reverse=True)
        return result
    except Exception as e:
        logger.warning(f"Error in match_catalog_categories_to_themes: {e}")
        return []


def get_upcoming_festivals(
    reference_date: Optional[date] = None,
    window_days: int = 45,
    catalog_categories: Optional[list[str]] = None
) -> List[Dict[str, Any]]:
    """
    Identifies active and upcoming commercial and cultural festivals occurring within window_days.
    Loads dynamic entries from SQLite `festival_calendar`.
    Matches against merchant's live catalog categories via semantic themes.
    """
    if reference_date is None:
        reference_date = date.today()

    # Resolve merchant's current catalog categories if not passed
    if catalog_categories is None:
        try:
            from backend.db import get_db
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT category FROM catalog WHERE stock > 0")
            catalog_categories = [r[0] for r in cursor.fetchall() if r[0]]
            conn.close()
        except Exception:
            catalog_categories = []

    # Fetch festivals from database
    festivals_db = []
    try:
        from backend.db import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, month, day, duration_days, themes, custom_categories, lift_multiplier, is_active FROM festival_calendar WHERE is_active = 1"
        )
        for row in cursor.fetchall():
            festivals_db.append(dict(row))
        conn.close()
    except Exception as e:
        logger.warning(f"Error querying festival_calendar: {e}")

    if not festivals_db:
        festivals_db = [
            {
                "id": 1,
                "name": "Onam Festive Season",
                "month": 9,
                "day": 5,
                "duration_days": 10,
                "themes": '["feast_cooking", "traditional_attire", "festive_gifting", "home_decor"]',
                "lift_multiplier": 1.35,
                "is_active": 1
            }
        ]

    active_festivals = []
    current_year = reference_date.year

    for fest in festivals_db:
        # Find the single closest occurrence (current year or next year)
        valid_occurrences = []
        for year in [current_year, current_year + 1]:
            try:
                fest_date = date(year, fest["month"], fest["day"])
            except ValueError:
                continue

            delta = (fest_date - reference_date).days
            duration = fest.get("duration_days", 7)
            if -duration <= delta <= window_days:
                valid_occurrences.append((delta, fest_date, duration))

        if not valid_occurrences:
            continue

        # Sort by proximity to reference date
        valid_occurrences.sort(key=lambda x: x[0] if x[0] >= -1 else 9999 + abs(x[0]))
        delta, fest_date, duration = valid_occurrences[0]
        
        # Retail & festival sales run early: active from `duration` days before the date up to 1 day post-event
        if -1 <= delta <= duration:
            status = "ongoing"
        elif delta > 0:
            status = "upcoming"
        else:
            status = "past"

        # Parse custom categories or compute dynamic theme matches
        custom_cats_raw = fest.get("custom_categories")
        if custom_cats_raw:
            try:
                matched_categories = json.loads(custom_cats_raw) if isinstance(custom_cats_raw, str) else custom_cats_raw
            except Exception:
                matched_categories = []
        else:
            themes_raw = fest.get("themes", "[]")
            try:
                themes_list = json.loads(themes_raw) if isinstance(themes_raw, str) else themes_raw
            except Exception:
                themes_list = []

            matched_info = match_catalog_categories_to_themes(catalog_categories, themes_list)
            matched_categories = [m["category"] for m in matched_info]

        themes_parsed = []
        if fest.get("themes"):
            try:
                themes_parsed = json.loads(fest["themes"]) if isinstance(fest["themes"], str) else fest["themes"]
            except Exception:
                themes_parsed = []

        active_festivals.append({
            "id": fest.get("id"),
            "name": fest["name"],
            "date": fest_date.isoformat(),
            "formatted_date": fest_date.strftime("%b %d"),
            "days_away": max(0, delta),
            "status": status,
            "lift_multiplier": float(fest.get("lift_multiplier", 1.35)),
            "categories": matched_categories,
            "themes": themes_parsed,
            "custom_categories": custom_cats_raw
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

    # 3. Cultural & Festival Pre-Shopping Elevators (with Dynamic Multipliers)
    for fest in upcoming_festivals:
        days_away = fest["days_away"]
        base_fest_lift = float(fest.get("lift_multiplier", 1.35))
        # Proximity weight: Closer festivals have stronger lift
        fest_lift = base_fest_lift if days_away <= 7 else (round(base_fest_lift * 0.95, 2) if days_away <= 15 else round(base_fest_lift * 0.90, 2))
        for cat in fest["categories"]:
            fest_reason = f"Festive Lift: {fest['name']} ({days_away} days away) driving category demand"
            if cat in category_boosts:
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
        "formatted_date": reference_dt.strftime("%A, %b %d, %Y"),
        "formatted_time": reference_dt.strftime("%I:%M %p"),
        "season": current_season,
        "season_label": season_meta["name"],
        "commercial_week": iso_week,
        "weather": weather_data,
        "upcoming_festivals": upcoming_festivals,
        "category_boosts": formatted_boosts
    }
