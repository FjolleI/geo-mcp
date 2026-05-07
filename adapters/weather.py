"""
Weather adapter — powered by Open-Meteo (free, no API key required).
Geocodes the city via Nominatim first, then fetches weather.
"""

import httpx
from adapters.geocoding import geocode

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


async def get_weather(city: str) -> dict:
    """Fetch current weather for a city name."""
    location = await geocode(city)
    if "error" in location:
        return location

    lat, lon = location["lat"], location["lon"]

    async with httpx.AsyncClient() as client:
        r = await client.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "weather_code",
                    "precipitation",
                ],
                "timezone": "auto",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

    current = data["current"]
    code = current.get("weather_code", 0)

    return {
        "city": location["display_name"].split(",")[0],
        "full_location": location["display_name"],
        "lat": lat,
        "lon": lon,
        "temperature_c": current["temperature_2m"],
        "feels_like_c": current["apparent_temperature"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_speed_kmh": current["wind_speed_10m"],
        "wind_direction_deg": current["wind_direction_10m"],
        "precipitation_mm": current["precipitation"],
        "condition": WMO_CODES.get(code, f"Unknown (WMO {code})"),
        "weather_code": code,
        "timezone": data.get("timezone", "unknown"),
        "source": "Open-Meteo",
    }
