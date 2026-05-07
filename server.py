"""
geo-mcp: A geospatial MCP server exposing weather, geocoding,
timezone, and nearby places to any MCP client (Claude, Cursor, etc.)
"""

from mcp.server.fastmcp import FastMCP
from adapters.geocoding import geocode, reverse_geocode
from adapters.weather import get_weather
from adapters.timezone import get_timezone
from adapters.places import nearby_places

mcp = FastMCP(name="geo-mcp")


@mcp.tool()
async def geocode_address(address: str) -> dict:
    """Convert a human-readable address into latitude and longitude coordinates."""
    return await geocode(address)


@mcp.tool()
async def reverse_geocode_coords(lat: float, lon: float) -> dict:
    """Convert latitude and longitude coordinates into a human-readable address."""
    return await reverse_geocode(lat, lon)


@mcp.tool()
async def current_weather(city: str) -> dict:
    """
    Get current weather for a city.
    Returns temperature (°C), wind speed, weather description, and feels-like temp.
    """
    return await get_weather(city)


@mcp.tool()
async def location_timezone(lat: float, lon: float) -> dict:
    """Get the timezone and current local time for a given latitude/longitude."""
    return await get_timezone(lat, lon)


@mcp.tool()
async def places_nearby(lat: float, lon: float, category: str, radius_m: int = 1000) -> dict:
    """
    Find nearby places of interest using OpenStreetMap.

    Categories: restaurant, cafe, hospital, pharmacy, school,
                supermarket, park, hotel, bank, gas_station
    """
    return await nearby_places(lat, lon, category, radius_m)


if __name__ == "__main__":
    mcp.run()
