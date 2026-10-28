import asyncio
from urllib.parse import parse_qs

import httpx

import adapters.geocoding as geocoding
import adapters.http as http
import adapters.weather as weather
import server


def _mock_http(monkeypatch, handler):
    requests = []

    def record(request):
        requests.append(request)
        return handler(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(http.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(record), **kw))
    monkeypatch.setattr(geocoding, "_cache", {})
    return requests


CURRENT = {"timezone": "Europe/Berlin", "current": {
    "temperature_2m": 11.0, "apparent_temperature": 9.5, "relative_humidity_2m": 80,
    "wind_speed_10m": 6.0, "wind_direction_10m": 230, "weather_code": 3, "precipitation": 0.0,
}}

DAILY = {"timezone": "Europe/Berlin", "daily": {
    "time": ["2026-10-28", "2026-10-29"],
    "weather_code": [3, 61],
    "temperature_2m_min": [6.1, 7.0],
    "temperature_2m_max": [12.3, 11.0],
    "precipitation_sum": [0.0, 4.2],
    "precipitation_probability_max": [10, 80],
    "wind_speed_10m_max": [14.0, 22.5],
    "sunrise": ["2026-10-28T06:58", "2026-10-29T07:00"],
    "sunset": ["2026-10-28T16:42", "2026-10-29T16:40"],
}}


def test_weather_by_coordinates_skips_geocoding(monkeypatch):
    requests = _mock_http(monkeypatch, lambda r: httpx.Response(200, json=CURRENT))
    result = asyncio.run(weather.get_weather(lat=52.52, lon=13.405))
    assert [r.url.host for r in requests] == ["api.open-meteo.com"]
    assert result["condition"] == "Overcast"
    assert result["lat"] == 52.52 and result["city"] is None


def test_weather_by_city(monkeypatch):
    def handler(request):
        if "nominatim" in request.url.host:
            return httpx.Response(200, json=[{"display_name": "Hamburg, Deutschland", "lat": "53.55", "lon": "10.0"}])
        return httpx.Response(200, json=CURRENT)

    _mock_http(monkeypatch, handler)
    result = asyncio.run(weather.get_weather("Hamburg"))
    assert result["city"] == "Hamburg"
    assert result["full_location"] == "Hamburg, Deutschland"
    assert result["temperature_c"] == 11.0


def test_weather_requires_a_location():
    assert asyncio.run(weather.get_weather())["status_code"] == 400
    assert asyncio.run(weather.get_weather(lat=52.5))["status_code"] == 400
    assert asyncio.run(weather.get_weather(lat=100, lon=0))["status_code"] == 400


def test_forecast(monkeypatch):
    requests = _mock_http(monkeypatch, lambda r: httpx.Response(200, json=DAILY))
    result = asyncio.run(weather.get_forecast(lat=52.52, lon=13.405, days=2))
    assert parse_qs(requests[0].url.query.decode())["forecast_days"] == ["2"]
    assert [d["date"] for d in result["days"]] == ["2026-10-28", "2026-10-29"]
    assert result["days"][1] == {
        "date": "2026-10-29", "condition": "Light rain", "weather_code": 61,
        "temp_min_c": 7.0, "temp_max_c": 11.0, "precipitation_mm": 4.2,
        "precipitation_probability_pct": 80, "wind_speed_max_kmh": 22.5,
        "sunrise": "2026-10-29T07:00", "sunset": "2026-10-29T16:40",
    }


def test_forecast_rejects_invalid_days():
    assert asyncio.run(weather.get_forecast(lat=52.5, lon=13.4, days=0))["status_code"] == 400
    assert asyncio.run(weather.get_forecast(lat=52.5, lon=13.4, days=17))["status_code"] == 400


def test_mcp_schema_lists_categories():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    category = tools["places_nearby"].inputSchema["properties"]["category"]
    assert category["enum"] == [
        "restaurant", "cafe", "hospital", "pharmacy", "school",
        "supermarket", "park", "hotel", "bank", "gas_station",
    ]
    assert {"current_weather", "weather_forecast"} <= tools.keys()
