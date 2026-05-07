"""
Geocoding adapter — powered by Nominatim (OpenStreetMap).
No API key required. Rate limit: 1 req/sec per OSM policy.
"""

import httpx

BASE_URL = "https://nominatim.openstreetmap.org"
HEADERS = {"User-Agent": "geo-mcp/1.0 (github.com/yourname/geo-mcp)"}


async def geocode(address: str) -> dict:
    """Address → lat/lon."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/search",
            params={"q": address, "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        results = r.json()

    if not results:
        return {"error": f"No results found for: {address}"}

    top = results[0]
    return {
        "address": address,
        "display_name": top["display_name"],
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
        "type": top.get("type", "unknown"),
        "source": "OpenStreetMap Nominatim",
    }


async def reverse_geocode(lat: float, lon: float) -> dict:
    """lat/lon → address."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

    if "error" in data:
        return {"error": data["error"]}

    addr = data.get("address", {})
    return {
        "lat": lat,
        "lon": lon,
        "display_name": data.get("display_name", "Unknown"),
        "city": addr.get("city") or addr.get("town") or addr.get("village", ""),
        "country": addr.get("country", ""),
        "postcode": addr.get("postcode", ""),
        "source": "OpenStreetMap Nominatim",
    }
