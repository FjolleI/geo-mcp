"""
Timezone adapter — uses timeapi.io (free, no key required).
"""

import httpx
from datetime import datetime

TIMEAPI_URL = "https://timeapi.io/api/time/current/coordinate"


async def get_timezone(lat: float, lon: float) -> dict:
    """Get timezone and current local time for a lat/lon coordinate."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            TIMEAPI_URL,
            params={"latitude": lat, "longitude": lon},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

    return {
        "lat": lat,
        "lon": lon,
        "timezone": data.get("timeZone", "unknown"),
        "current_local_time": data.get("dateTime", "unknown"),
        "utc_offset": data.get("utcOffset", "unknown"),
        "day_of_week": data.get("dayOfWeek", "unknown"),
        "dst_active": data.get("dstActive", False),
        "source": "timeapi.io",
    }
