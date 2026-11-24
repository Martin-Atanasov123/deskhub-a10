"""Weather: place lookup, parsing, and the "not set up" message. No network (a fake HTTP client).

    uv run python tests/test_weather.py
"""
import json
import pathlib
import tempfile

from deskhub.weather import Weather, parse

problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"http {self.status}")


FORECAST = {
    "current": {"temperature_2m": 12.34, "apparent_temperature": 10.0, "relative_humidity_2m": 71.0,
                "weather_code": 61, "is_day": 1, "wind_speed_10m": 14.6},
    "hourly": {"time": [1000, 4600], "temperature_2m": [12.0, 11.5], "weather_code": [61, 3],
               "precipitation_probability": [80, None]},
    "daily": {"time": [0, 86400], "temperature_2m_max": [14.0, 15.2], "temperature_2m_min": [8.0, 9.1],
              "weather_code": [61, 0], "precipitation_probability_max": [90, 5]},
}
GEO = {"results": [{"name": "Springfield", "admin1": "Illinois", "country": "United States", "country_code": "US",
                    "latitude": 39.8, "longitude": -89.6},
                   {"name": "Springfield", "admin1": "Missouri", "country": "United States", "country_code": "US",
                    "latitude": 37.2, "longitude": -93.3}]}


class FakeHttp:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return Resp(GEO if "geocoding" in url else FORECAST)


tmp = pathlib.Path(tempfile.mkdtemp()) / "place.json"

# not set up: no network, a clear message
http = FakeHttp()
w = Weather({}, http=http, cache_path=tmp)
check(not w.configured(), "empty config is not configured")
check(w.poll() == {"type": "weather", "error": "not_configured"}, "not configured message")
check(http.calls == [], "nothing is fetched until the location is set")

# city: looked up once, remembered on disk
w = Weather({"city": "Springfield, Missouri"}, http=http, cache_path=tmp)
msg = w.poll()
check(msg["type"] == "weather" and msg["place"] == "Springfield", f"place name: {msg.get('place')}")
check(http.calls[0][1]["name"] == "Springfield", "geocoding searches the city part only")
check(abs(http.calls[1][1]["latitude"] - 37.2) < 1e-6, f"the Missouri match was used: {http.calls[1][1]}")
check(json.loads(tmp.read_text())["place"]["latitude"] == 37.2, "place remembered")
n = len(http.calls)
w2 = Weather({"city": "Springfield, Missouri"}, http=http, cache_path=tmp)
w2.poll()
check(len(http.calls) == n + 1, "a remembered place is not looked up again (only the forecast is fetched)")
check(Weather({"city": "Other"}, http=http, cache_path=tmp).configured(), "another city is configured")

# coordinates: no lookup at all
http2 = FakeHttp()
w = Weather({"latitude": 51.5, "longitude": -0.1, "name": "Home"}, http=http2, cache_path=tmp)
msg = w.poll()
check(len(http2.calls) == 1 and "forecast" in http2.calls[0][0], "coordinates skip geocoding")
check(msg["place"] == "Home", "name label used")

# parsing and units
check(msg["unit"] == "C" and msg["wind_unit"] == "km/h", "metric by default")
check(msg["temp"] == 12.3 and msg["humidity"] == 71 and msg["wind"] == 15 and msg["is_day"] is True, f"current: {msg}")
check(msg["hours"][1] == {"t": 4600, "temp": 11.5, "code": 3, "precip": 0}, f"null precipitation becomes 0: {msg['hours']}")
check(msg["days"][0]["hi"] == 14.0 and msg["days"][1]["code"] == 0, "daily")
imp = Weather({"latitude": 1, "longitude": 2, "units": "imperial"}, http=http2, cache_path=tmp)
imp.poll()
params = http2.calls[-1][1]
check(params["temperature_unit"] == "fahrenheit" and params["wind_speed_unit"] == "mph", "imperial asks for F and mph")
check(parse({"name": "x"}, True, FORECAST)["unit"] == "F", "parse unit")

# errors raise (the companion keeps the last good message and retries)
class Bad(FakeHttp):
    def get(self, url, params=None, timeout=None):
        return Resp({}, 500)


try:
    Weather({"latitude": 1, "longitude": 2}, http=Bad(), cache_path=tmp).poll()
    check(False, "an HTTP error must raise")
except RuntimeError:
    pass

print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
raise SystemExit(1 if problems else 0)
