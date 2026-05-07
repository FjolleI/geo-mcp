from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from adapters.geocoding import geocode, reverse_geocode
from adapters.weather import get_weather
from adapters.timezone import get_timezone
from adapters.places import nearby_places

app = FastAPI(
    title="geo-mcp",
    description="Geospatial API wrapper for Claude MCP services",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


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
            "/weather?city=...",
            "/timezone?lat=...&lon=...",
            "/places?lat=...&lon=...&category=...&radius_m=...",
        ],
    }


@app.get("/geocode")
async def geocode_route(address: str = Query(..., description="The address to geocode")):
    return await geocode(address)


@app.get("/reverse-geocode")
async def reverse_geocode_route(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    return await reverse_geocode(lat, lon)


@app.get("/weather")
async def weather_route(city: str = Query(..., description="City name")):
    return await get_weather(city)


@app.get("/timezone")
async def timezone_route(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    return await get_timezone(lat, lon)


@app.get("/places")
async def places_route(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    category: str = Query(..., description="Place category"),
    radius_m: int = Query(1000, description="Search radius in meters"),
):
    result = await nearby_places(lat, lon, category, radius_m)
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(result, status_code=result.get("status_code", 400))
    return result
