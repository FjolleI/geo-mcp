"""
geo-mcp: A geospatial MCP server exposing weather, geocoding,
timezone, and nearby places to any MCP client (Claude, Cursor, etc.)
"""

from typing import Literal

from mcp.server.fastmcp import FastMCP
from adapters.geocoding import geocode, reverse_geocode
from adapters.weather import get_forecast, get_weather
from adapters.timezone import get_timezone
from adapters.places import CATEGORY_MAP, nearby_places

mcp = FastMCP(name="geo-mcp")

# Valid values show up as an enum in the tool schema.
Category = Literal[tuple(CATEGORY_MAP)]


@mcp.tool()
async def geocode_address(address: str, limit: int = 1, language: str | None = None) -> dict:
    """
    Convert a human-readable address into latitude and longitude coordinates.
    For ambiguous names (e.g. "Frankfurt", "Springfield") set limit (max 10):
    "results" then lists the candidates. language: e.g. "de" or "en" for
    display names; default is the local language of the place.
    """
    return await geocode(address, limit, language)


@mcp.tool()
async def reverse_geocode_coords(lat: float, lon: float, language: str | None = None) -> dict:
    """
    Convert latitude and longitude coordinates into a human-readable address.
    language: e.g. "de" or "en"; default is the local language of the place.
    """
    return await reverse_geocode(lat, lon, language)


@mcp.tool()
async def current_weather(
    city: str | None = None, lat: float | None = None, lon: float | None = None,
    language: str | None = None,
) -> dict:
    """
    Get current weather for a city name or for lat/lon coordinates.
    Prefer lat/lon when known; it skips the geocoding step.
    language (e.g. "de") applies to the resolved location name.
    Returns temperature (°C), wind speed, weather description, and feels-like temp.
    """
    return await get_weather(city, lat, lon, language)


@mcp.tool()
async def weather_forecast(
    city: str | None = None, lat: float | None = None, lon: float | None = None, days: int = 3,
    language: str | None = None,
) -> dict:
    """
    Get a daily weather forecast (today first) for a city name or lat/lon.
    days: 1-16. Each day has condition, min/max temperature (°C),
    precipitation (mm and max probability %), max wind speed, sunrise and sunset.
    language (e.g. "de") applies to the resolved location name.
    """
    return await get_forecast(city, lat, lon, days, language)


@mcp.tool()
async def location_timezone(lat: float, lon: float) -> dict:
    """Get the timezone and current local time for a given latitude/longitude."""
    return await get_timezone(lat, lon)


@mcp.tool()
async def places_nearby(lat: float, lon: float, category: Category, radius_m: int = 1000) -> dict:
    """
    Find nearby places of interest using OpenStreetMap.
    Each place has "open_now" (yes/no/unknown), already evaluated for the
    place's local time including public holidays, and "next_change" (local
    time when that state ends, e.g. closing time). Report "unknown" honestly
    instead of guessing.
    Returns up to 10 places: open first, then unknown, then closed, each
    group sorted by "distance_m". radius_m is limited to 5000.
    Where recorded in OSM, places also have cuisine, wheelchair,
    outdoor_seating and takeaway.
    """
    return await nearby_places(lat, lon, category, radius_m)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
