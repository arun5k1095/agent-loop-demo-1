"""Flask tool server. The agent never calls OpenWeatherMap directly; it calls this.

Run from the project root:  python tool_server/app.py
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # lets this script import config.py from the project root

from weather import WeatherError, get_weather

app = Flask(__name__)


@app.get("/weather")
def weather_endpoint():
    """GET /weather?city=London -> {"city": "London", "temp_c": 14.2, "description": "light rain"}"""
    city = request.args.get("city", "").strip()
    if not city or len(city) > 100:
        return jsonify(error="query parameter 'city' is required (max 100 characters)"), 400
    try:
        return jsonify(get_weather(city))
    except WeatherError as exc:
        return jsonify(error=str(exc)), 502  # 502: the failure is behind this server, not the caller's fault


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)  # local only
