"""
Nearby places adapter — powered by Overpass API (OpenStreetMap).
No API key required.
"""

import asyncio
import math
import re
import httpx
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import humanized_opening_hours as hoh
from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "geo-mcp/1.0 (github.com/fjollei/geo-mcp)", "Accept": "application/json"}
# The public Overpass instance regularly takes 30s+ to answer, mostly queueing.
TIMEOUT = httpx.Timeout(60, connect=10)
RETRY_STATUS = {429, 502, 503, 504}
# Larger radii make Overpass queries slow enough to time out.
MAX_RADIUS_M = 5000
MAX_RESULTS = 10
# Overpass returns elements in no particular order, so fetch enough to find the nearest.
FETCH_LIMIT = 200

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
}


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


_RANGE = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")


def _split_midnight(opening_hours: str) -> tuple[str, list[time]]:
    """
    The parser cannot handle ranges past midnight ("10:00-01:00").
    Such ranges are truncated to "10:00-24:00"; the post-midnight end
    times are collected so the following day can be checked separately.
    """
    overflow: list[time] = []

    def repl(m: re.Match) -> str:
        h1, m1, h2, m2 = map(int, m.groups())
        if (h2, m2) == (0, 0):  # "until 00:00" means "until midnight"
            return f"{h1:02d}:{m1:02d}-24:00"
        if (h2, m2) <= (h1, m1) or h2 >= 24:
            h2 = h2 - 24 if h2 >= 24 else h2  # also handles "25:00" notation
            overflow.append(time(h2, m2))
            return f"{h1:02d}:{m1:02d}-24:00"
        return m.group(0)

    return _RANGE.sub(repl, opening_hours), overflow


def _open_now(opening_hours: str, lat: float, lon: float) -> str:
    """Evaluate the OSM value for the current local time: yes / no / unknown."""
    if not opening_hours:
        return "unknown"
    try:
        tz = _tf.timezone_at(lat=lat, lng=lon) or "UTC"
        now = datetime.now(ZoneInfo(tz)).replace(tzinfo=None)
        return "yes" if _is_open(opening_hours, now) else "no"
    except Exception:
        # e.g. sunrise/sunset or malformed values
        return "unknown"


def _is_open(opening_hours: str, now: datetime) -> bool:
    cleaned, overflow = _split_midnight(opening_hours)
    oh = hoh.OHParser(cleaned)
    if oh.is_open(now):
        return True
    # After midnight: open if the place was open until 24:00 yesterday
    # and the extended closing time has not been reached yet.
    late = [t for t in overflow if now.time() < t]
    if late:
        yesterday_end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=0)
        return oh.is_open(yesterday_end)
    return False


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


def _build_places(elements: list[dict], lat: float, lon: float) -> list[dict]:
    """Named places, open first, then unknown, then closed; nearest first within each."""
    places = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
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
            "open_now": _open_now(oh, el_lat, el_lon),
        })

    rank = {"yes": 0, "unknown": 1, "no": 2}
    places.sort(key=lambda p: (rank[p["open_now"]], p["distance_m"]))
    return places


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

    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as client:
        try:
            r = await client.post(OVERPASS_URL, data={"data": query})
            if r.status_code in RETRY_STATUS:
                # The public instance is often overloaded; one retry usually helps.
                await asyncio.sleep(2)
                r = await client.post(OVERPASS_URL, data={"data": query})
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            return {
                "error": "Overpass API request failed",
                "status_code": exc.response.status_code,
                "details": exc.response.text,
            }
        except httpx.TimeoutException:
            return {
                "error": f"Overpass API did not respond within {TIMEOUT.read:.0f}s. "
                "The service is probably busy; try again later or with a smaller radius.",
            }
        except Exception as exc:
            return {"error": f"Nearby places request failed: {type(exc).__name__}: {exc}"}

    places = _build_places(data.get("elements", []), lat, lon)
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
