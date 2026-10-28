import asyncio
import time
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

import adapters.geocoding as geocoding
import adapters.http as http
import adapters.timezone as timezone
import adapters.weather as weather
import app as app_module


def _mock_http(monkeypatch, handler):
    """Route all outgoing adapter requests to handler; returns the list of requests."""
    requests = []

    def record(request):
        requests.append(request)
        return handler(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(http.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(record), **kw))
    return requests


@pytest.fixture(autouse=True)
def fresh_nominatim(monkeypatch):
    monkeypatch.setattr(geocoding, "_cache", {})
    monkeypatch.setattr(geocoding, "_last_request", 0.0)
    monkeypatch.setattr(geocoding, "_lock", asyncio.Lock())


# --- timezone ---------------------------------------------------------------

def test_timezone_berlin():
    result = asyncio.run(timezone.get_timezone(52.52, 13.405))
    assert result["timezone"] == "Europe/Berlin"
    assert result["utc_offset"] in {"+01:00", "+02:00"}
    assert result["dst_active"] is (result["utc_offset"] == "+02:00")
    assert result["day_of_week"] in {"Monday", "Tuesday", "Wednesday", "Thursday",
                                     "Friday", "Saturday", "Sunday"}
    datetime.fromisoformat(result["current_local_time"])


def test_timezone_half_hour_offset():
    assert asyncio.run(timezone.get_timezone(28.61, 77.21))["utc_offset"] == "+05:30"  # Delhi


def test_timezone_negative_offset():
    assert asyncio.run(timezone.get_timezone(40.71, -74.01))["utc_offset"] in {"-05:00", "-04:00"}


def test_timezone_rejects_invalid_coordinates():
    result = asyncio.run(timezone.get_timezone(95, 0))
    assert result["status_code"] == 400


# --- shared HTTP helper -----------------------------------------------------

def test_http_error_becomes_service_error(monkeypatch):
    _mock_http(monkeypatch, lambda r: httpx.Response(500))
    with pytest.raises(http.ServiceError) as exc:
        asyncio.run(http.request_json("GET", "https://example.test", service="Example"))
    assert exc.value.status_code == 502
    assert "HTTP 500" in str(exc.value)


def test_timeout_becomes_service_error(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    _mock_http(monkeypatch, handler)
    with pytest.raises(http.ServiceError) as exc:
        asyncio.run(http.request_json("GET", "https://example.test", service="Example"))
    assert exc.value.status_code == 504
    assert "did not respond" in str(exc.value)


def test_invalid_json_becomes_service_error(monkeypatch):
    _mock_http(monkeypatch, lambda r: httpx.Response(200, text="<html>"))
    with pytest.raises(http.ServiceError):
        asyncio.run(http.request_json("GET", "https://example.test", service="Example"))


def test_retry_once_on_overload(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(http.asyncio, "sleep", lambda s: real_sleep(0))
    answers = iter([httpx.Response(502), httpx.Response(200, json={"ok": True})])
    requests = _mock_http(monkeypatch, lambda r: next(answers))
    assert asyncio.run(http.request_json("GET", "https://example.test", service="X", retry=True)) == {"ok": True}
    assert len(requests) == 2


def test_no_retry_by_default(monkeypatch):
    requests = _mock_http(monkeypatch, lambda r: httpx.Response(502))
    with pytest.raises(http.ServiceError):
        asyncio.run(http.request_json("GET", "https://example.test", service="X"))
    assert len(requests) == 1


# --- adapters return errors instead of raising ------------------------------

def test_geocode_reports_upstream_error(monkeypatch):
    _mock_http(monkeypatch, lambda r: httpx.Response(503))
    result = asyncio.run(geocoding.geocode("Berlin"))
    assert result["status_code"] == 502
    assert "Nominatim" in result["error"]


def test_weather_reports_upstream_error(monkeypatch):
    def handler(request):
        if "nominatim" in request.url.host:
            return httpx.Response(200, json=[{"display_name": "Berlin, Deutschland",
                                              "lat": "52.52", "lon": "13.40"}])
        return httpx.Response(500)

    _mock_http(monkeypatch, handler)
    result = asyncio.run(weather.get_weather("Berlin"))
    assert "Open-Meteo" in result["error"]


# --- Nominatim usage policy -------------------------------------------------

def test_nominatim_results_are_cached(monkeypatch):
    requests = _mock_http(monkeypatch, lambda r: httpx.Response(
        200, json=[{"display_name": "Berlin", "lat": "52.52", "lon": "13.40"}]))

    async def twice():
        return await geocoding.geocode("Berlin"), await geocoding.geocode("Berlin")

    first, second = asyncio.run(twice())
    assert first == second
    assert len(requests) == 1


def test_nominatim_is_throttled(monkeypatch):
    monkeypatch.setattr(geocoding, "MIN_INTERVAL_S", 0.3)
    _mock_http(monkeypatch, lambda r: httpx.Response(
        200, json=[{"display_name": "X", "lat": "1", "lon": "2"}]))

    async def three():
        await asyncio.gather(*(geocoding.geocode(city) for city in ["A", "B", "C"]))

    start = time.monotonic()
    asyncio.run(three())
    assert time.monotonic() - start >= 0.6


# --- HTTP wrapper -----------------------------------------------------------

def test_app_maps_errors_to_status_codes(monkeypatch):
    client = TestClient(app_module.app)
    assert client.get("/timezone", params={"lat": 95, "lon": 0}).status_code == 400
    assert client.get("/places", params={"lat": 52.5, "lon": 13.4, "category": "zoo"}).status_code == 400

    _mock_http(monkeypatch, lambda r: httpx.Response(503))
    assert client.get("/geocode", params={"address": "Berlin"}).status_code == 502

    ok = client.get("/timezone", params={"lat": 52.52, "lon": 13.405})
    assert ok.status_code == 200
    assert ok.json()["timezone"] == "Europe/Berlin"
