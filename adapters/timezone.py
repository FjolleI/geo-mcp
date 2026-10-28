"""
Timezone adapter — computed locally with timezonefinder and zoneinfo.
No network access, no API key.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()


def timezone_name(lat: float, lon: float) -> str | None:
    """IANA timezone for a coordinate, e.g. 'Europe/Berlin'."""
    return _tf.timezone_at(lat=lat, lng=lon)


def local_now(lat: float, lon: float) -> datetime:
    """Current time at a coordinate (timezone-aware; UTC if the zone is unknown)."""
    return datetime.now(ZoneInfo(timezone_name(lat, lon) or "UTC"))


def _format_offset(now: datetime) -> str:
    minutes = int(now.utcoffset().total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


async def get_timezone(lat: float, lon: float) -> dict:
    """Get timezone and current local time for a lat/lon coordinate."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {"error": "lat must be within -90..90 and lon within -180..180", "status_code": 400}

    tz = timezone_name(lat, lon)
    if not tz:
        return {"error": f"No timezone found for {lat}, {lon}", "status_code": 404}

    now = datetime.now(ZoneInfo(tz))
    return {
        "lat": lat,
        "lon": lon,
        "timezone": tz,
        "current_local_time": now.replace(microsecond=0, tzinfo=None).isoformat(),
        "utc_offset": _format_offset(now),
        "day_of_week": now.strftime("%A"),
        "dst_active": bool(now.dst()),
        "source": "timezonefinder (local)",
    }
