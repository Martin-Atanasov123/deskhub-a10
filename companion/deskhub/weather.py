"""Weather for the browser display, from Open-Meteo (free, no account).

The PC fetches it, so the phone makes no internet requests of its own (less battery, one
place that knows the location). Nothing is fetched until [weather] is set in config.toml:

    [weather]
    city = "London"            # looked up once, then remembered
    # latitude = 51.51         # or give the coordinates yourself
    # longitude = -0.13
    # name = "Home"            # label shown on the page
    units = "metric"           # or "imperial"
"""
import json
import logging
import pathlib
import time

import httpx

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
CACHE_FILE = pathlib.Path.home() / ".deskhub" / "weather_place.json"


def geocode(query: str, http) -> dict:
    """First match for "City" or "City, Region/Country", as {name, latitude, longitude}."""
    name, _, hint = (p.strip() for p in query.partition(","))
    r = http.get(GEOCODE_URL, params={"name": name, "count": 10, "language": "en"}, timeout=15)
    r.raise_for_status()
    places = r.json().get("results") or []
    if hint:
        h = hint.lower()
        places = [p for p in places if h in str(p.get("admin1", "")).lower()
                  or h in str(p.get("country", "")).lower() or h == str(p.get("country_code", "")).lower()] or places
    if not places:
        raise ValueError(f"no place called {query!r}")
    p = places[0]
    return {"name": p.get("name", name), "latitude": float(p["latitude"]), "longitude": float(p["longitude"])}


def parse(place: dict, imperial: bool, data: dict) -> dict:
    """Open-Meteo's answer in the shape the browser page uses."""
    cur, h, d = data["current"], data["hourly"], data["daily"]
    hours = [{"t": t, "temp": round(tp, 1), "code": c, "precip": p or 0}
             for t, tp, c, p in zip(h["time"], h["temperature_2m"], h["weather_code"], h["precipitation_probability"])]
    days = [{"t": t, "hi": round(hi, 1), "lo": round(lo, 1), "code": c, "precip": p or 0}
            for t, hi, lo, c, p in zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"],
                                       d["weather_code"], d["precipitation_probability_max"])]
    return {
        "type": "weather", "place": place["name"], "fetched": int(time.time()),
        "unit": "F" if imperial else "C", "wind_unit": "mph" if imperial else "km/h",
        "temp": round(cur["temperature_2m"], 1), "feels": round(cur["apparent_temperature"], 1),
        "humidity": int(cur["relative_humidity_2m"]), "wind": round(cur["wind_speed_10m"]),
        "code": int(cur["weather_code"]), "is_day": bool(cur["is_day"]),
        "hours": hours, "days": days,
    }


class Weather:
    def __init__(self, cfg: dict, http=None, cache_path: pathlib.Path = CACHE_FILE):
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.http = http
        self.cache_path = cache_path
        self.imperial = str(self.cfg.get("units", "metric")).lower() == "imperial"
        self.place: dict | None = None

    def configured(self) -> bool:
        return bool(self.cfg.get("city") or ("latitude" in self.cfg and "longitude" in self.cfg))

    def _client(self):
        if self.http is None:
            self.http = httpx.Client(headers={"User-Agent": "deskhub-companion"})
        return self.http

    def resolve_place(self) -> dict:
        if self.place:
            return self.place
        if "latitude" in self.cfg and "longitude" in self.cfg:
            self.place = {"name": str(self.cfg.get("name") or self.cfg.get("city") or "Weather"),
                          "latitude": float(self.cfg["latitude"]), "longitude": float(self.cfg["longitude"])}
            return self.place
        query = str(self.cfg["city"]).strip()
        try:
            cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if cached.get("query") == query:
                self.place = cached["place"]
        except (OSError, ValueError, KeyError):
            pass
        if not self.place:
            self.place = geocode(query, self._client())
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(json.dumps({"query": query, "place": self.place}), encoding="utf-8")
            except OSError as e:
                log.debug("could not remember the place: %s", e)
        if self.cfg.get("name"):
            self.place = {**self.place, "name": str(self.cfg["name"])}
        return self.place

    def poll(self) -> dict:
        """The weather message (a "not set up" one when [weather] is empty). Blocking: run in a thread."""
        if not self.configured():
            return {"type": "weather", "error": "not_configured"}
        place = self.resolve_place()
        params = {
            "latitude": place["latitude"], "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,wind_speed_10m",
            "hourly": "temperature_2m,weather_code,precipitation_probability",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto", "timeformat": "unixtime", "forecast_days": 6, "forecast_hours": 24,
            "wind_speed_unit": "mph" if self.imperial else "kmh",
        }
        if self.imperial:
            params["temperature_unit"] = "fahrenheit"
        r = self._client().get(FORECAST_URL, params=params, timeout=15)
        r.raise_for_status()
        return parse(place, self.imperial, r.json())
