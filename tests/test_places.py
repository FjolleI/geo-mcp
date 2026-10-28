import asyncio
from datetime import datetime, time
from urllib.parse import parse_qs

import httpx
import pytest

import adapters.places as places


# Wednesday 2026-10-28
@pytest.mark.parametrize("oh, now, expected", [
    ("Mo-Su 08:00-20:00", datetime(2026, 10, 28, 12, 0), True),
    ("Mo-Su 08:00-20:00", datetime(2026, 10, 28, 21, 0), False),
    ("Mo-Fr 09:00-17:00; Sa 10:00-14:00", datetime(2026, 10, 31, 11, 0), True),
    ("Mo-Fr 09:00-17:00; Sa 10:00-14:00", datetime(2026, 11, 1, 11, 0), False),
    ("24/7", datetime(2026, 10, 28, 3, 0), True),
    # Ranges past midnight
    ("Mo-Su 10:00-01:00", datetime(2026, 10, 28, 23, 0), True),
    ("Mo-Su 10:00-01:00", datetime(2026, 10, 29, 0, 30), True),
    ("Mo-Su 10:00-01:00", datetime(2026, 10, 29, 2, 0), False),
    ("We 18:00-02:00", datetime(2026, 10, 29, 1, 0), True),   # Thursday night, open from Wednesday
    ("We 18:00-02:00", datetime(2026, 10, 28, 1, 0), False),  # Wednesday night, Tuesday was closed
    ("Mo-Su 18:00-00:00", datetime(2026, 10, 28, 23, 30), True),
])
def test_is_open(oh, now, expected):
    assert places._is_open(oh, now) is expected


def test_split_midnight():
    assert places._split_midnight("Mo-Su 10:00-01:00") == ("Mo-Su 10:00-24:00", [time(1, 0)])
    assert places._split_midnight("Fr 20:00-26:00") == ("Fr 20:00-24:00", [time(2, 0)])
    assert places._split_midnight("Mo 18:00-00:00") == ("Mo 18:00-24:00", [])
    assert places._split_midnight("Mo 08:00-12:00") == ("Mo 08:00-12:00", [])


def test_open_now_unknown_for_missing_or_unparsable():
    assert places._open_now("", 52.52, 13.40) == "unknown"
    assert places._open_now("sunrise-sunset", 52.52, 13.40) in {"yes", "no", "unknown"}
    assert places._open_now("this is not a schedule", 52.52, 13.40) == "unknown"


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
    monkeypatch.setattr(places, "_open_now", lambda oh, lat, lon: status[oh])
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
