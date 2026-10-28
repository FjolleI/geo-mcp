"""
Nearby places adapter — powered by Overpass API (OpenStreetMap).
No API key required.
"""

import math
import httpx
from datetime import datetime

from opening_hours import OpeningHours, State

from adapters.http import ServiceError, request_json

# Tried in order. The main instance regularly takes 30s+ to answer (mostly
# queueing), so it gets a shorter timeout before falling back to the next one.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
FALLBACK_TIMEOUT = httpx.Timeout(20, connect=5)
TIMEOUT = httpx.Timeout(60, connect=10)
# Larger radii make Overpass queries slow enough to time out.
MAX_RADIUS_M = 5000
MAX_RESULTS = 10
# Overpass returns elements in no particular order, so fetch enough to find the nearest.
FETCH_LIMIT = 200

_STATE = {State.OPEN: "yes", State.CLOSED: "no", State.UNKNOWN: "unknown"}

CATEGORY_MAP = {
    "restaurant": ("amenity", "restaurant"),
    "cafe": ("amenity", "cafe"),
    "hospital": ("amenity", "hospital"),
    "pharmacy": ("amenity", "pharmacy"),
    "school": ("amenity", "school"),
    "supermarket": ("shop", "supermarket"),
    "park": ("leisure", "park"),
    "hotel": ("tourism", "hotel"),
    "bank": ("amenity", "bank"),
    "gas_station": ("amenity", "fuel"),
    "atm": ("amenity", "atm"),
    "bar": ("amenity", "bar"),
    "pub": ("amenity", "pub"),
    "fast_food": ("amenity", "fast_food"),
    "bakery": ("shop", "bakery"),
    "doctor": ("amenity", "doctors"),
    "dentist": ("amenity", "dentist"),
    "toilets": ("amenity", "toilets"),
    "parking": ("amenity", "parking"),
    "charging_station": ("amenity", "charging_station"),
    "museum": ("tourism", "museum"),
    "post_office": ("amenity", "post_office"),
    "police": ("amenity", "police"),
}

# Often mapped without a name; these are still worth listing.
UNNAMED_OK = {"atm", "toilets", "parking", "charging_station"}

# Optional OSM tags passed through when present.
EXTRA_TAGS = ["cuisine", "wheelchair", "outdoor_seating", "takeaway"]


def _build_query(lat: float, lon: float, key: str, value: str, radius: int) -> str:
    return f"""
[out:json][timeout:25];
(
  node["{key}"="{value}"](around:{radius},{lat},{lon});
  way["{key}"="{value}"](around:{radius},{lat},{lon});
  relation["{key}"="{value}"](around:{radius},{lat},{lon});
);
out center {FETCH_LIMIT};
"""


def _opening_state(opening_hours: str, lat: float, lon: float, now: datetime | None = None) -> dict:
    """
    Evaluate the OSM value at the place's local time (timezone and public
    holidays are derived from the coordinates).
    open_now is yes / no / unknown; next_change is when that state ends.
    """
    if not opening_hours:
        return {"open_now": "unknown", "next_change": None}
    try:
        oh = OpeningHours(opening_hours, coords=(lat, lon))
        state, _comment = oh.state(now)
        change = oh.next_change(now)
    except Exception:
        # malformed value
        return {"open_now": "unknown", "next_change": None}
    return {
        "open_now": _STATE[state],
        "next_change": change.replace(tzinfo=None).isoformat(timespec="minutes") if change else None,
    }


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Great-circle distance in meters (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(a)))


def _address(tags: dict) -> str:
    """'Street 1, 10115 Berlin' from addr:* tags; empty if none are recorded."""
    street = " ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")]))
    city = " ".join(filter(None, [tags.get("addr:postcode"), tags.get("addr:city")]))
    return ", ".join(filter(None, [street, city]))


def _name(tags: dict, category: str) -> str | None:
    """Name, else brand/operator; unnamed places only for categories where that is normal."""
    name = tags.get("name") or tags.get("brand") or tags.get("operator")
    if not name and category in UNNAMED_OK:
        name = category.replace("_", " ").capitalize()
    return name


def _build_places(elements: list[dict], lat: float, lon: float, category: str = "") -> list[dict]:
    """Places, open first, then unknown, then closed; nearest first within each."""
    places = []
    for el in elements:
        tags = el.get("tags", {})
        name = _name(tags, category)
        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lon = el.get("lon") or el.get("center", {}).get("lon")
        if not name or el_lat is None or el_lon is None:
            continue

        oh = tags.get("opening_hours", "")
        places.append({
            "name": name,
            "lat": el_lat,
            "lon": el_lon,
            "distance_m": _distance_m(lat, lon, el_lat, el_lon),
            "address": _address(tags),
            "phone": tags.get("phone", tags.get("contact:phone", "")),
            "website": tags.get("website", tags.get("contact:website", "")),
            "opening_hours": oh or "not recorded",
            **_opening_state(oh, el_lat, el_lon),
            **{t: tags[t] for t in EXTRA_TAGS if t in tags},
        })

    rank = {"yes": 0, "unknown": 1, "no": 2}
    places.sort(key=lambda p: (rank[p["open_now"]], p["distance_m"]))
    return places


async def _overpass(query: str) -> dict:
    """Run a query, falling back to the next instance on errors or timeouts."""
    for url in OVERPASS_URLS[:-1]:
        try:
            return await request_json("POST", url, service="Overpass API",
                                      timeout=FALLBACK_TIMEOUT, data={"data": query})
        except ServiceError:
            continue
    # Last instance: full timeout, and one retry since overload is usually brief.
    return await request_json("POST", OVERPASS_URLS[-1], service="Overpass API",
                              timeout=TIMEOUT, retry=True, data={"data": query})


async def nearby_places(lat: float, lon: float, category: str, radius_m: int = 1000) -> dict:
    """Find nearby places by category using OpenStreetMap Overpass API."""
    tag = CATEGORY_MAP.get(category.lower())
    if not tag:
        valid = list(CATEGORY_MAP.keys())
        return {"error": f"Unknown category '{category}'. Valid options: {valid}"}
    if radius_m <= 0:
        return {"error": "radius_m must be positive"}

    requested_radius = radius_m
    radius_m = min(radius_m, MAX_RADIUS_M)
    key, value = tag
    query = _build_query(lat, lon, key, value, radius_m)

    try:
        data = await _overpass(query)
    except ServiceError as exc:
        return exc.to_dict()

    places = _build_places(data.get("elements", []), lat, lon, category.lower())
    result = {
        "category": category,
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m,
        "count": min(len(places), MAX_RESULTS),
        "total_found": len(places),
        "places": places[:MAX_RESULTS],
        "source": "OpenStreetMap Overpass API",
    }
    if requested_radius > radius_m:
        result["note"] = f"radius_m was limited to {MAX_RADIUS_M}"
    return result
