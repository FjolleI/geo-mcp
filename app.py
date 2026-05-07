from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from adapters.geocoding import geocode, reverse_geocode
from adapters.weather import get_weather
from adapters.timezone import get_timezone
from adapters.places import nearby_places


def bad_request(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


async def health(request):
    return JSONResponse({"status": "ok"})


async def root(request):
    return JSONResponse(
        {
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
    )


async def geocode_route(request):
    address = request.query_params.get("address")
    if not address:
        return bad_request("Missing required query parameter: address")
    return JSONResponse(await geocode(address))


async def reverse_geocode_route(request):
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    if lat is None or lon is None:
        return bad_request("Missing required query parameters: lat and lon")
    try:
        return JSONResponse(await reverse_geocode(float(lat), float(lon)))
    except ValueError:
        return bad_request("Query parameters lat and lon must be numeric")


async def weather_route(request):
    city = request.query_params.get("city")
    if not city:
        return bad_request("Missing required query parameter: city")
    return JSONResponse(await get_weather(city))


async def timezone_route(request):
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    if lat is None or lon is None:
        return bad_request("Missing required query parameters: lat and lon")
    try:
        return JSONResponse(await get_timezone(float(lat), float(lon)))
    except ValueError:
        return bad_request("Query parameters lat and lon must be numeric")


async def places_route(request):
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    category = request.query_params.get("category")
    radius_m = request.query_params.get("radius_m", "1000")

    if lat is None or lon is None or not category:
        return bad_request(
            "Missing required query parameters: lat, lon, and category"
        )

    try:
        return JSONResponse(
            await nearby_places(
                float(lat), float(lon), category, int(radius_m)
            )
        )
    except ValueError:
        return bad_request(
            "Query parameters lat, lon must be numeric and radius_m must be an integer"
        )


app = Starlette(
    debug=False,
    routes=[
        Route("/", root),
        Route("/healthz", health),
        Route("/geocode", geocode_route),
        Route("/reverse-geocode", reverse_geocode_route),
        Route("/weather", weather_route),
        Route("/timezone", timezone_route),
        Route("/places", places_route),
    ],
)
