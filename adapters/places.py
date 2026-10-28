"""
Nearby places adapter — powered by Overpass API (OpenStreetMap).
No API key required.
"""

import re
import httpx
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import humanized_opening_hours as hoh
from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "geo-mcp/1.0 (github.com/fjollei/geo-mcp)", "Accept": "application/json"}

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
[out:json][timeout:10];
(
  node["{key}"="{value}"](around:{radius},{lat},{lon});
  way["{key}"="{value}"](around:{radius},{lat},{lon});
  relation["{key}"="{value}"](around:{radius},{lat},{lon});
);
out center 50;
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


async def nearby_places(lat: float, lon: float, category: str, radius_m: int = 1000) -> dict:
    """Find nearby places by category using OpenStreetMap Overpass API."""
    tag = CATEGORY_MAP.get(category.lower())
    if not tag:
        valid = list(CATEGORY_MAP.keys())
        return {"error": f"Unknown category '{category}'. Valid options: {valid}"}

    key, value = tag
    query = _build_query(lat, lon, key, value, radius_m)

    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            r = await client.post(OVERPASS_URL, data={"data": query}, timeout=15)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            return {
                "error": "Overpass API request failed",
                "status_code": exc.response.status_code,
                "details": exc.response.text,
            }
        except Exception as exc:
            return {"error": f"Nearby places request failed: {exc}"}

    places = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lon = el.get("lon") or el.get("center", {}).get("lon")

        oh = tags.get("opening_hours", "")
        places.append({
            "name": name,
            "lat": el_lat,
            "lon": el_lon,
            "address": tags.get("addr:street", "") + " " + tags.get("addr:housenumber", ""),
            "phone": tags.get("phone", tags.get("contact:phone", "")),
            "website": tags.get("website", tags.get("contact:website", "")),
            "opening_hours": oh or "not recorded",
            "open_now": _open_now(oh, el_lat, el_lon),
        })

    # Open first, then unknown, then closed
    rank = {"yes": 0, "unknown": 1, "no": 2}
    places.sort(key=lambda p: rank[p["open_now"]])

    return {
        "category": category,
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m,
        "count": len(places),
        "places": places[:10],
        "source": "OpenStreetMap Overpass API",
    }
