# 🌍 geo-mcp

> Connect Claude or any MCP client to live location intelligence — weather, geocoding, timezone, and nearby places — using only free open APIs.

[Live demo on Render](https://geo-mcp-exoi.onrender.com) • [Swagger docs](https://geo-mcp-exoi.onrender.com/docs) • [GitHub repo](https://github.com/FjolleI/geo-mcp)

---

## What it does

`geo-mcp` exposes a lightweight MCP surface for real-world geospatial queries. It provides:

- `geocode_address` — address to latitude/longitude
- `reverse_geocode_coords` — location to human-readable address
- `current_weather` — live weather for a city or coordinates
- `weather_forecast` — daily forecast for up to 16 days
- `location_timezone` — timezone and local time for coordinates
- `places_nearby` — nearby points of interest from OpenStreetMap

Built for developers, open source, and fast integration with modern tools.

| Tool | Description | API Used |
|------|-------------|----------|
| `geocode_address` | Address → lat/lon | Nominatim (OSM) |
| `reverse_geocode_coords` | lat/lon → address | Nominatim (OSM) |
| `current_weather` | Live weather for a city or lat/lon | Open-Meteo |
| `weather_forecast` | Daily forecast, 1–16 days | Open-Meteo |
| `location_timezone` | Timezone + local time | computed locally (timezonefinder) |
| `places_nearby` | POIs within a radius, with opening status | Overpass (OSM) |

All APIs are **free and open** — no signup, no keys. Errors from upstream services are returned as an `error` field instead of crashing the tool. Nominatim results are cached and requests are throttled to 1 per second, as its usage policy requires.

---

## Quick start

```bash
git clone https://github.com/fjollei/geo-mcp
cd geo-mcp
pip install -r requirements.txt
python server.py
```

### Run with uvx

No clone or virtualenv needed — [uv](https://docs.astral.sh/uv/) installs and runs it in one step:

```bash
uvx --from git+https://github.com/FjolleI/geo-mcp geo-mcp
```

From a local checkout: `uvx --from . geo-mcp`

### Run with Docker

```bash
docker build -t geo-mcp .
docker run -p 8000:8000 geo-mcp
```

## Live demo
[Live geo-mcp on Render](https://geo-mcp-exoi.onrender.com)

### Deploy as an HTTP service

This repo now includes `app.py`, a lightweight HTTP wrapper around the same adapter logic used by the MCP server. It is useful for Render and other container hosts.

- Health check: `/healthz`
- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`
- Reverse proxy docs: `/redoc`
- Geocode: `/geocode?address=...&limit=...&language=...`
- Reverse geocode: `/reverse-geocode?lat=...&lon=...&language=...`
- Weather: `/weather?city=...` or `/weather?lat=...&lon=...`
- Forecast: `/forecast?city=...&days=...` or `/forecast?lat=...&lon=...&days=...`
- Timezone: `/timezone?lat=...&lon=...`
- Nearby places: `/places?lat=...&lon=...&category=...&radius_m=...`

---

## Connect to Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "geo-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/geo-mcp/server.py"]
    }
  }
}
```

Or, using uvx (no local checkout required):

```json
{
  "mcpServers": {
    "geo-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/FjolleI/geo-mcp", "geo-mcp"]
    }
  }
}
```

Config file location:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop — you'll see the 🔨 tools icon appear.

---

## Example prompts

Once connected, try these in Claude:

```
What's the weather like in Tokyo right now?
```
```
Find me hospitals within 500m of the Eiffel Tower.
```
```
What time is it right now in lat 35.6762, lon 139.6503?
```
```
Which cafés near Alexanderplatz are open right now?
```
```
Will it rain in Vienna in the next three days?
```
```
Geocode "1600 Pennsylvania Ave NW, Washington DC"
```

---

## Project structure

```
geo-mcp/
├── server.py              # FastMCP server + tool definitions
├── app.py                 # HTTP wrapper (FastAPI) for container hosts
├── adapters/
│   ├── http.py            # Shared HTTP helper: timeouts, retries, error messages
│   ├── geocoding.py       # Nominatim geocoder (cached, 1 req/s)
│   ├── weather.py         # Open-Meteo weather
│   ├── timezone.py        # Local timezone lookup
│   └── places.py          # Overpass POI search + opening hours
├── tests/                 # pytest suite
├── .github/workflows/     # CI: tests + uvx start
├── pyproject.toml         # Packaging + `geo-mcp` entry point (uvx)
├── requirements.txt
└── Dockerfile
```

---

## Tool reference

### `geocode_address(address, limit=1, language=None)`

Returns the best match. With `limit` > 1 (max 10), `results` lists the candidates — useful for ambiguous names. `language` (e.g. `"de"`, `"en"`) sets the language of names; by default Nominatim uses the local language of the place. `reverse_geocode_coords`, `current_weather` and `weather_forecast` accept `language` too.

```json
{
  "display_name": "Frankfurt, Hesse, Germany",
  "lat": 50.1106,
  "lon": 8.6821,
  "type": "city",
  "results": [
    { "display_name": "Frankfurt, Hesse, Germany", "lat": 50.1106, "lon": 8.6821, "type": "city" },
    { "display_name": "Frankfurt (Oder), Brandenburg, Germany", "lat": 52.3471, "lon": 14.5506, "type": "town" }
  ]
}
```

### `current_weather(city=None, lat=None, lon=None)`

Pass a city name or `lat`/`lon` (skips geocoding).

```json
{
  "city": "London",
  "temperature_c": 14.2,
  "feels_like_c": 12.8,
  "humidity_pct": 76,
  "wind_speed_kmh": 18.4,
  "condition": "Partly cloudy",
  "precipitation_mm": 0.0
}
```

### `weather_forecast(city=None, lat=None, lon=None, days=3)`

```json
{
  "city": "Wien",
  "timezone": "Europe/Vienna",
  "days": [
    {
      "date": "2026-10-29",
      "condition": "Overcast",
      "temp_min_c": 9.8,
      "temp_max_c": 12.4,
      "precipitation_mm": 0.0,
      "precipitation_probability_pct": 90,
      "wind_speed_max_kmh": 12.0,
      "sunrise": "2026-10-29T06:35",
      "sunset": "2026-10-29T16:40"
    }
  ]
}
```

### `places_nearby(lat, lon, category, radius_m)`

Supported categories: `restaurant`, `cafe`, `hospital`, `pharmacy`, `school`, `supermarket`, `park`, `hotel`, `bank`, `gas_station`, `atm`, `bar`, `pub`, `fast_food`, `bakery`, `doctor`, `dentist`, `toilets`, `parking`, `charging_station`, `museum`, `post_office`, `police`

Places without a name use their brand or operator. Unnamed ATMs, toilets, parking and charging stations are listed too. Where recorded in OSM, places include `cuisine`, `wheelchair`, `outdoor_seating` and `takeaway`.

Returns up to 10 places: open first, then unknown, then closed, each group sorted by distance. `open_now` is evaluated from the OSM `opening_hours` tag for the place's local time, including public holidays; `next_change` is when that state ends (e.g. closing time). `radius_m` is limited to 5000. If the main Overpass instance is slow or down, a second instance is used.

```json
{
  "category": "cafe",
  "radius_m": 500,
  "count": 10,
  "total_found": 38,
  "places": [
    {
      "name": "Monmouth Coffee",
      "lat": 51.513,
      "lon": -0.122,
      "distance_m": 140,
      "address": "Monmouth Street 27, WC2H 9EU London",
      "opening_hours": "Mo-Fr 07:30-18:00",
      "open_now": "yes",
      "next_change": "2026-10-28T18:00",
      "cuisine": "coffee_shop",
      "wheelchair": "yes"
    }
  ]
}
```

### Running the tests

```bash
uv run --group dev pytest
```

---

## Why this project

Built to demonstrate the **multi-adapter MCP pattern** — the same architecture used in production fleet/telematics MCP servers. Each adapter is:

- Independently testable
- Easily swappable (swap Nominatim for Google Maps, Open-Meteo for OpenWeather, etc.)
- Async-first with `httpx`
- Typed with clear return schemas

This maps directly to real-world MCP server jobs that require connecting multiple vendor APIs under a unified tool layer.

---

## Extending it

Want to add a new data source? Create `adapters/yourapi.py`:

```python
import httpx

async def your_tool(param: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.example.com/...", timeout=10)
        r.raise_for_status()
        return r.json()
```

Then register it in `server.py`:

```python
from adapters.yourapi import your_tool

@mcp.tool()
async def exposed_tool_name(param: str) -> dict:
    """Tool description shown to the AI."""
    return await your_tool(param)
```

---

## Tech stack

- **[FastMCP](https://github.com/jlowin/fastmcp)** — MCP server framework
- **[httpx](https://www.python-httpx.org/)** — async HTTP client
- **[Open-Meteo](https://open-meteo.com/)** — free weather API
- **[Nominatim](https://nominatim.org/)** — OpenStreetMap geocoding
- **[Overpass API](https://overpass-api.de/)** — OpenStreetMap POI data
- **[opening-hours-py](https://github.com/remi-dupre/opening-hours-rs)** — OSM opening hours evaluation
- **[timezonefinder](https://github.com/jannikmi/timezonefinder)** — offline timezone lookup

---

## License

MIT
