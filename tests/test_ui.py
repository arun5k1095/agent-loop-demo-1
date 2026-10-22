import unittest
from unittest.mock import patch

import httpx
from groq import APIConnectionError, APIStatusError

from ui_server.app import app


class AskEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_success_returns_answer_and_steps(self):
        with patch("ui_server.app.run_agent", return_value="OK"):
            response = self.client.post("/ask", json={"question": "Hello"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"answer": "OK", "steps": []})

    def test_connection_failure_returns_safe_json(self):
        error = APIConnectionError(request=httpx.Request("POST", "https://example.test"))
        with patch("ui_server.app.run_agent", side_effect=error):
            response = self.client.post("/ask", json={"question": "Hello"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("trusted certificates", response.json["error"])
        self.assertEqual(response.json["steps"], [])

    def test_provider_rejection_does_not_expose_details(self):
        error = APIStatusError(
            "private provider details",
            response=httpx.Response(401, request=httpx.Request("POST", "https://example.test")),
            body=None,
        )
        with patch("ui_server.app.run_agent", side_effect=error):
            response = self.client.post("/ask", json={"question": "Hello"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private provider details", response.get_data(as_text=True))

    def test_invalid_question_is_rejected_before_agent_runs(self):
        with patch("ui_server.app.run_agent") as run_agent:
            response = self.client.post("/ask", json={"question": " "})
        self.assertEqual(response.status_code, 400)
        run_agent.assert_not_called()