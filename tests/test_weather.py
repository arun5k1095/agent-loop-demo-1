import unittest
from unittest.mock import Mock, patch

from tool_server import weather


class WeatherConfigurationTests(unittest.TestCase):
    def test_weather_uses_key_from_json_loader(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "name": "Paris", "main": {"temp": 18}, "weather": [{"description": "clear sky"}]
        }
        with patch.object(weather, "load_secrets", return_value={"OPENWEATHER_API_KEY": "test-weather-value"}), patch.object(
            weather.requests, "get", return_value=response
        ) as request:
            self.assertEqual(weather.get_weather("Paris")["temp_c"], 18)
        self.assertEqual(request.call_args.kwargs["params"]["appid"], "test-weather-value")