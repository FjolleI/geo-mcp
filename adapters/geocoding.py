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


MAX_LIMIT = 10


def _params(language: str | None, **params) -> dict:
    # Without accept-language, Nominatim answers in the local language of each place.
    return {**params, "format": "json", **({"accept-language": language} if language else {})}


def _result(item: dict) -> dict:
    return {
        "display_name": item["display_name"],
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "type": item.get("type", "unknown"),
    }


async def geocode(address: str, limit: int = 1, language: str | None = None) -> dict:
    """
    Address → lat/lon of the best match. With limit > 1, "results" also lists
    up to that many candidates, for ambiguous names like "Springfield".
    language: e.g. "de" or "en" for display names.
    """
    if not 1 <= limit <= MAX_LIMIT:
        return {"error": f"limit must be within 1..{MAX_LIMIT}", "status_code": 400}
    try:
        results = await _nominatim("/search", _params(language, q=address, limit=limit))
    except ServiceError as exc:
        return exc.to_dict()

    if not results:
        return {"error": f"No results found for: {address}", "status_code": 404}

    result = {"address": address, **_result(results[0])}
    if limit > 1:
        result["results"] = [_result(item) for item in results]
    result["source"] = "OpenStreetMap Nominatim"
    return result


async def reverse_geocode(lat: float, lon: float, language: str | None = None) -> dict:
    """lat/lon → address. language: e.g. "de" or "en"."""
    try:
        data = await _nominatim("/reverse", _params(language, lat=lat, lon=lon))
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
