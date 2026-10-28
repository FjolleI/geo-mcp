import asyncio
from datetime import datetime
from urllib.parse import parse_qs

import httpx
import pytest
from zoneinfo import ZoneInfo

import adapters.places as places


BERLIN = (52.52, 13.405)
TZ = ZoneInfo("Europe/Berlin")


def _at(*args):
    return datetime(*args, tzinfo=TZ)


# Wednesday 2026-10-28
@pytest.mark.parametrize("oh, now, expected", [
    ("Mo-Su 08:00-20:00", _at(2026, 10, 28, 12, 0), "yes"),
    ("Mo-Su 08:00-20:00", _at(2026, 10, 28, 21, 0), "no"),
    ("Mo-Fr 09:00-17:00; Sa 10:00-14:00", _at(2026, 10, 31, 11, 0), "yes"),
    ("Mo-Fr 09:00-17:00; Sa 10:00-14:00", _at(2026, 11, 1, 11, 0), "no"),
    ("24/7", _at(2026, 10, 28, 3, 0), "yes"),
    # Ranges past midnight
    ("Mo-Su 10:00-01:00", _at(2026, 10, 28, 23, 0), "yes"),
    ("Mo-Su 10:00-01:00", _at(2026, 10, 29, 0, 30), "yes"),
    ("Mo-Su 10:00-01:00", _at(2026, 10, 29, 2, 0), "no"),
    ("We 18:00-02:00", _at(2026, 10, 29, 1, 0), "yes"),   # Thursday night, open from Wednesday
    ("We 18:00-02:00", _at(2026, 10, 28, 1, 0), "no"),    # Wednesday night, Tuesday was closed
    ("Fr 20:00-26:00", _at(2026, 10, 31, 1, 0), "yes"),
    # Public holidays are derived from the coordinates (Christmas in Germany)
    ("Mo-Fr 08:00-18:00; PH off", _at(2026, 12, 25, 10, 0), "no"),
    ("Mo-Fr 08:00-18:00; PH off", _at(2026, 12, 22, 10, 0), "yes"),
    ("sunrise-sunset", _at(2026, 10, 28, 12, 0), "yes"),
    ("sunrise-sunset", _at(2026, 10, 28, 22, 0), "no"),
    ("Mo-Fr 08:00-18:00 unknown", _at(2026, 10, 28, 10, 0), "unknown"),
])
def test_opening_state(oh, now, expected):
    assert places._opening_state(oh, *BERLIN, now)["open_now"] == expected


def test_opening_state_uses_local_time_of_the_place():
    # 17:30 UTC is 18:30 in Berlin: closed there
    utc = datetime(2026, 10, 28, 17, 30, tzinfo=ZoneInfo("UTC"))
    assert places._opening_state("Mo-Su 08:00-18:00", *BERLIN, utc)["open_now"] == "no"


def test_opening_state_next_change():
    state = places._opening_state("Mo-Su 10:00-01:00", *BERLIN, _at(2026, 10, 28, 23, 0))
    assert state == {"open_now": "yes", "next_change": "2026-10-29T01:00"}


def test_opening_state_unknown_for_missing_or_malformed():
    assert places._opening_state("", *BERLIN)["open_now"] == "unknown"
    assert places._opening_state("this is not a schedule", *BERLIN) == {"open_now": "unknown", "next_change": None}


def test_distance_m():
    assert places._distance_m(52.52, 13.405, 52.52, 13.405) == 0
    # Brandenburger Tor -> Alexanderplatz, about 2.3 km
    assert 2200 < places._distance_m(52.5163, 13.3777, 52.5219, 13.4132) < 2500


def test_address():
    assert places._address({}) == ""
    assert places._address({"addr:street": "Unter den Linden", "addr:housenumber": "1"}) == "Unter den Linden 1"
    assert places._address({"addr:postcode": "10117", "addr:city": "Berlin"}) == "10117 Berlin"
    assert places._address({
        "addr:street": "Unter den Linden", "addr:housenumber": "1",
        "addr:postcode": "10117", "addr:city": "Berlin",
    }) == "Unter den Linden 1, 10117 Berlin"


def _node(name, lat, lon, **tags):
    return {"type": "node", "lat": lat, "lon": lon, "tags": {"name": name, **tags}}


def test_build_places_sorts_by_status_then_distance(monkeypatch):
    status = {"Open far": "yes", "Open near": "yes", "Closed near": "no", "Unknown": "unknown"}
    monkeypatch.setattr(places, "_opening_state",
                        lambda oh, lat, lon: {"open_now": status[oh], "next_change": None})
    elements = [
        _node("Closed near", 52.5201, 13.405, opening_hours="Closed near"),
        _node("Open far", 52.53, 13.405, opening_hours="Open far"),
        _node("Unknown", 52.521, 13.405, opening_hours="Unknown"),
        _node("Open near", 52.5205, 13.405, opening_hours="Open near"),
        {"type": "node", "lat": 52.52, "lon": 13.405, "tags": {"amenity": "cafe"}},  # unnamed
        {"type": "way", "center": {"lat": 52.522, "lon": 13.405},
         "tags": {"name": "Way", "opening_hours": "Unknown"}},
    ]
    result = places._build_places(elements, 52.52, 13.405)
    assert [p["name"] for p in result] == ["Open near", "Open far", "Unknown", "Way", "Closed near"]
    assert result[0]["distance_m"] < result[1]["distance_m"]


def _run_with_overpass(monkeypatch, elements, **kwargs):
    queries = []

    def handler(request):
        queries.append(parse_qs(request.content.decode())["data"][0])
        return httpx.Response(200, json={"elements": elements})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(places.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    return asyncio.run(places.nearby_places(52.52, 13.405, "cafe", **kwargs)), queries


def test_nearby_places_limits_results_and_counts(monkeypatch):
    elements = [_node(f"Cafe {i}", 52.52 + i * 0.0001, 13.405) for i in range(15)]
    result, _ = _run_with_overpass(monkeypatch, elements)
    assert result["count"] == 10
    assert result["total_found"] == 15
    assert len(result["places"]) == 10
    assert result["places"][0]["name"] == "Cafe 0"
    assert "note" not in result


def test_nearby_places_clamps_radius(monkeypatch):
    result, queries = _run_with_overpass(monkeypatch, [], radius_m=50000)
    assert result["radius_m"] == places.MAX_RADIUS_M
    assert "note" in result
    assert f"around:{places.MAX_RADIUS_M}," in queries[0]


def test_nearby_places_rejects_bad_input():
    assert "error" in asyncio.run(places.nearby_places(52.52, 13.405, "cafe", radius_m=0))
    assert "error" in asyncio.run(places.nearby_places(52.52, 13.405, "zoo"))


def _mock_overpass_hosts(monkeypatch, handler):
    hosts = []

    def record(request):
        hosts.append(request.url.host)
        return handler(request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(places.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(record), **kw))
    return hosts


def test_overpass_falls_back_to_next_instance(monkeypatch):
    def handler(request):
        if request.url.host == "overpass-api.de":
            raise httpx.ReadTimeout("busy", request=request)
        return httpx.Response(200, json={"elements": [_node("Cafe", 52.52, 13.405)]})

    hosts = _mock_overpass_hosts(monkeypatch, handler)
    result = asyncio.run(places.nearby_places(52.52, 13.405, "cafe"))
    assert hosts == ["overpass-api.de", "overpass.openstreetmap.fr"]
    assert result["places"][0]["name"] == "Cafe"


def test_overpass_uses_first_instance_when_it_works(monkeypatch):
    hosts = _mock_overpass_hosts(monkeypatch, lambda r: httpx.Response(200, json={"elements": []}))
    asyncio.run(places.nearby_places(52.52, 13.405, "cafe"))
    assert hosts == ["overpass-api.de"]


def test_overpass_reports_error_when_all_instances_fail(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr("adapters.http.asyncio.sleep", lambda s: real_sleep(0))
    hosts = _mock_overpass_hosts(monkeypatch, lambda r: httpx.Response(503))
    result = asyncio.run(places.nearby_places(52.52, 13.405, "cafe"))
    assert result["status_code"] == 502
    assert "Overpass" in result["error"]
    # first instance once, last instance with one retry
    assert hosts == ["overpass-api.de", "overpass.openstreetmap.fr", "overpass.openstreetmap.fr"]
