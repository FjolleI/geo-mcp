# 🌍 geo-mcp

> A geospatial MCP server that gives Claude (or any MCP client) real-world location superpowers — weather, geocoding, timezone, and nearby places. Zero API keys required.

---

## What it does

Connect Claude Desktop, Cursor, or any MCP client to live geospatial data through 5 clean tools:

| Tool | Description | API Used |
|------|-------------|----------|
| `geocode_address` | Address → lat/lon | Nominatim (OSM) |
| `reverse_geocode_coords` | lat/lon → address | Nominatim (OSM) |
| `current_weather` | Live weather for any city | Open-Meteo |
| `location_timezone` | Timezone + local time | timeapi.io |
| `places_nearby` | POIs within a radius | Overpass (OSM) |

All APIs are **free and open** — no signup, no keys, no rate-limit surprises for personal use.

---

## Quick start

```bash
git clone https://github.com/yourname/geo-mcp
cd geo-mcp
pip install -r requirements.txt
python server.py
```

### Run with Docker

```bash
docker build -t geo-mcp .
docker run -p 8000:8000 geo-mcp
```

### Deploy as an HTTP service

This repo now includes `app.py`, a lightweight HTTP wrapper around the same adapter logic used by the MCP server. It is useful for Render and other container hosts.

- Health check: `/healthz`
- Geocode: `/geocode?address=...`
- Reverse geocode: `/reverse-geocode?lat=...&lon=...`
- Weather: `/weather?city=...`
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
Geocode "1600 Pennsylvania Ave NW, Washington DC"
```

---

## Project structure

```
geo-mcp/
├── server.py              # FastMCP server + tool definitions
├── adapters/
│   ├── geocoding.py       # Nominatim geocoder
│   ├── weather.py         # Open-Meteo weather
│   ├── timezone.py        # timeapi.io timezone
│   └── places.py          # Overpass POI search
├── requirements.txt
├── Dockerfile
└── claude_desktop_config.json
```

---

## Tool reference

### `geocode_address(address: str)`
```json
{
  "display_name": "Paris, Île-de-France, France",
  "lat": 48.8566,
  "lon": 2.3522,
  "type": "city"
}
```

### `current_weather(city: str)`
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

### `places_nearby(lat, lon, category, radius_m)`

Supported categories: `restaurant`, `cafe`, `hospital`, `pharmacy`, `school`, `supermarket`, `park`, `hotel`, `bank`, `gas_station`

```json
{
  "category": "cafe",
  "count": 8,
  "places": [
    { "name": "Monmouth Coffee", "lat": 51.513, "lon": -0.122, "opening_hours": "Mo-Fr 07:30-18:00" }
  ]
}
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
- **[timeapi.io](https://timeapi.io/)** — timezone lookup

---

## License

MIT
