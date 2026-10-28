from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from adapters.geocoding import geocode, reverse_geocode
from adapters.weather import get_forecast, get_weather
from adapters.timezone import get_timezone
from adapters.places import nearby_places

app = FastAPI(
    title="geo-mcp",
    description="Geospatial API wrapper for Claude MCP services",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


def _respond(result: dict):
    """Adapter errors are dicts with "error" (and an optional "status_code")."""
    if result.get("error"):
        return JSONResponse(result, status_code=result.get("status_code", 400))
    return result


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "service": "geo-mcp",
        "endpoints": [
            "/healthz",
            "/geocode?address=...",
            "/reverse-geocode?lat=...&lon=...",
            "/weather?city=... (or lat=...&lon=...)",
            "/forecast?city=...&days=... (or lat=...&lon=...)",
            "/timezone?lat=...&lon=...",
            "/places?lat=...&lon=...&category=...&radius_m=...",
        ],
    }


@app.get("/geocode")
async def geocode_route(
    address: str = Query(..., description="The address to geocode"),
    limit: int = Query(1, description="Number of candidates (1-10)"),
    language: str | None = Query(None, description='Language for names, e.g. "de"'),
):
    return _respond(await geocode(address, limit, language))


@app.get("/reverse-geocode")
async def reverse_geocode_route(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    language: str | None = Query(None, description='Language for names, e.g. "de"'),
):
    return _respond(await reverse_geocode(lat, lon, language))


@app.get("/weather")
async def weather_route(
    city: str | None = Query(None, description="City name (or use lat/lon)"),
    lat: float | None = Query(None, description="Latitude"),
    lon: float | None = Query(None, description="Longitude"),
    language: str | None = Query(None, description='Language for names, e.g. "de"'),
):
    return _respond(await get_weather(city, lat, lon, language))


@app.get("/forecast")
async def forecast_route(
    city: str | None = Query(None, description="City name (or use lat/lon)"),
    lat: float | None = Query(None, description="Latitude"),
    lon: float | None = Query(None, description="Longitude"),
    days: int = Query(3, description="Number of days (1-16)"),
    language: str | None = Query(None, description='Language for names, e.g. "de"'),
):
    return _respond(await get_forecast(city, lat, lon, days, language))


@app.get("/timezone")
async def timezone_route(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    return _respond(await get_timezone(lat, lon))


@app.get("/places")
async def places_route(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    category: str = Query(..., description="Place category"),
    radius_m: int = Query(1000, description="Search radius in meters"),
):
    return _respond(await nearby_places(lat, lon, category, radius_m))
