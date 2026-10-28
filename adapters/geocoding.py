"""
Geocoding adapter — powered by Nominatim (OpenStreetMap).
No API key required. The usage policy allows at most 1 request per second
and asks clients to cache results, so both are enforced here.
"""

import asyncio
import time

from adapters.http import ServiceError, request_json

BASE_URL = "https://nominatim.openstreetmap.org"

MIN_INTERVAL_S = 1.0
CACHE_TTL_S = 24 * 3600
CACHE_MAX = 1000

_lock = asyncio.Lock()
_last_request = 0.0
_cache: dict[tuple, tuple[float, object]] = {}


async def _nominatim(path: str, params: dict):
    """GET a Nominatim endpoint, cached and throttled to 1 request/second."""
    key = (path, tuple(sorted(params.items())))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]

    global _last_request
    async with _lock:
        wait = _last_request + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            data = await request_json("GET", f"{BASE_URL}{path}", service="Nominatim", params=params)
        finally:
            _last_request = time.monotonic()

    if len(_cache) >= CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.monotonic(), data)
    return data


async def geocode(address: str) -> dict:
    """Address → lat/lon."""
    try:
        results = await _nominatim("/search", {"q": address, "format": "json", "limit": 1})
    except ServiceError as exc:
        return exc.to_dict()

    if not results:
        return {"error": f"No results found for: {address}", "status_code": 404}

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
    try:
        data = await _nominatim("/reverse", {"lat": lat, "lon": lon, "format": "json"})
    except ServiceError as exc:
        return exc.to_dict()

    if "error" in data:
        return {"error": data["error"], "status_code": 404}

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
