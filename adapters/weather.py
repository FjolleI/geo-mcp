"""
Weather adapter — powered by Open-Meteo (free, no API key required).
Geocodes the city via Nominatim first, then fetches weather.
"""

from adapters.geocoding import geocode
from adapters.http import ServiceError, request_json

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


MAX_FORECAST_DAYS = 16


async def _resolve_location(city: str | None, lat: float | None, lon: float | None) -> dict:
    """Location from coordinates (preferred, no geocoding) or a city name."""
    if lat is not None and lon is not None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return {"error": "lat must be within -90..90 and lon within -180..180", "status_code": 400}
        return {"lat": lat, "lon": lon, "city": None, "full_location": None}
    if not city:
        return {"error": "Provide either city or both lat and lon", "status_code": 400}

    location = await geocode(city)
    if "error" in location:
        return location
    return {
        "lat": location["lat"],
        "lon": location["lon"],
        "city": location["display_name"].split(",")[0],
        "full_location": location["display_name"],
    }


async def _open_meteo(lat: float, lon: float, **params) -> dict:
    return await request_json(
        "GET", WEATHER_URL, service="Open-Meteo",
        params={"latitude": lat, "longitude": lon, "timezone": "auto", **params},
    )


def _condition(code: int) -> str:
    return WMO_CODES.get(code, f"Unknown (WMO {code})")


async def get_weather(city: str | None = None, lat: float | None = None, lon: float | None = None) -> dict:
    """Fetch current weather for a city name or coordinates."""
    location = await _resolve_location(city, lat, lon)
    if "error" in location:
        return location

    try:
        data = await _open_meteo(
            location["lat"], location["lon"],
            current=[
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "wind_speed_10m",
                "wind_direction_10m",
                "weather_code",
                "precipitation",
            ],
        )
    except ServiceError as exc:
        return exc.to_dict()

    current = data["current"]
    code = current.get("weather_code", 0)

    return {
        **location,
        "temperature_c": current["temperature_2m"],
        "feels_like_c": current["apparent_temperature"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_speed_kmh": current["wind_speed_10m"],
        "wind_direction_deg": current["wind_direction_10m"],
        "precipitation_mm": current["precipitation"],
        "condition": _condition(code),
        "weather_code": code,
        "timezone": data.get("timezone", "unknown"),
        "source": "Open-Meteo",
    }


async def get_forecast(
    city: str | None = None, lat: float | None = None, lon: float | None = None, days: int = 3,
) -> dict:
    """Daily forecast (today first) for a city name or coordinates."""
    if not 1 <= days <= MAX_FORECAST_DAYS:
        return {"error": f"days must be within 1..{MAX_FORECAST_DAYS}", "status_code": 400}
    location = await _resolve_location(city, lat, lon)
    if "error" in location:
        return location

    fields = [
        "weather_code",
        "temperature_2m_min",
        "temperature_2m_max",
        "precipitation_sum",
        "precipitation_probability_max",
        "wind_speed_10m_max",
        "sunrise",
        "sunset",
    ]
    try:
        data = await _open_meteo(location["lat"], location["lon"], daily=fields, forecast_days=days)
    except ServiceError as exc:
        return exc.to_dict()

    daily = data["daily"]
    forecast = [
        {
            "date": date,
            "condition": _condition(daily["weather_code"][i]),
            "weather_code": daily["weather_code"][i],
            "temp_min_c": daily["temperature_2m_min"][i],
            "temp_max_c": daily["temperature_2m_max"][i],
            "precipitation_mm": daily["precipitation_sum"][i],
            "precipitation_probability_pct": daily["precipitation_probability_max"][i],
            "wind_speed_max_kmh": daily["wind_speed_10m_max"][i],
            "sunrise": daily["sunrise"][i],
            "sunset": daily["sunset"][i],
        }
        for i, date in enumerate(daily["time"])
    ]
    return {
        **location,
        "timezone": data.get("timezone", "unknown"),
        "days": forecast,
        "source": "Open-Meteo",
    }
