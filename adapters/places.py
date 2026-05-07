"""
Nearby places adapter — powered by Overpass API (OpenStreetMap).
No API key required.
"""

import httpx

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
out center 10;
"""


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

        places.append({
            "name": name,
            "lat": el_lat,
            "lon": el_lon,
            "address": tags.get("addr:street", "") + " " + tags.get("addr:housenumber", ""),
            "phone": tags.get("phone", tags.get("contact:phone", "")),
            "website": tags.get("website", tags.get("contact:website", "")),
            "opening_hours": tags.get("opening_hours", ""),
        })

    return {
        "category": category,
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m,
        "count": len(places),
        "places": places[:10],
        "source": "OpenStreetMap Overpass API",
    }
