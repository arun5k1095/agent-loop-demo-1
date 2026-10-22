"""Calls OpenWeatherMap. app.py is the only caller."""

import requests

from config import load_secrets

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
TIMEOUT_SECONDS = 10


class WeatherError(Exception):
    """The forecast could not be fetched. The message is safe to send back to the caller."""


def get_weather(city: str) -> dict:
    """Return {"city", "temp_c", "description"} for a city, or raise WeatherError."""
    params = {"q": city, "units": "metric", "appid": load_secrets()["OPENWEATHER_API_KEY"]}
    try:
        response = requests.get(OPENWEATHER_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # SECURITY: str(exc) can contain the full request URL, including the API key, so it must not be passed on.
        raise WeatherError(f"could not reach OpenWeatherMap ({type(exc).__name__})") from exc

    data = response.json()  # OpenWeatherMap answers with JSON on errors too, e.g. {"cod": "404", "message": "city not found"}
    if response.status_code != 200:
        raise WeatherError(f"OpenWeatherMap returned {response.status_code}: {data.get('message', '')}")

    return {
        "city": data["name"],
        "temp_c": data["main"]["temp"],
        "description": data["weather"][0]["description"],
    }