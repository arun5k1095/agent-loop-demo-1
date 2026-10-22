import ssl
import unittest
from unittest.mock import patch

from agent import llm


class AskTests(unittest.TestCase):
    def setUp(self):
        secrets = patch.object(llm, "load_secrets", return_value={"GROQ_API_KEY": "test-groq-value"})
        secrets.start()
        self.addCleanup(secrets.stop)

    def test_ask_uses_verified_system_certificates_and_closes_client(self):
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(llm, "Groq") as groq_class, patch.object(
            llm.httpx, "Client"
        ) as http_client:
            client = groq_class.return_value
            expected = client.chat.completions.create.return_value.choices[0].message

            self.assertIs(llm.ask(messages, []), expected)

            context = http_client.call_args.kwargs["verify"]
            self.assertIsInstance(context, llm.truststore.SSLContext)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertEqual(groq_class.call_args.kwargs["timeout"], 60.0)
            self.assertEqual(groq_class.call_args.kwargs["api_key"], "test-groq-value")
            client.chat.completions.create.assert_called_once_with(
                model=llm.MODEL,
                messages=messages,
                tools=[],
                tool_choice="auto",
                max_completion_tokens=2000,
            )
            client.close.assert_called_once()

    def test_ask_closes_client_when_request_fails(self):
        with patch.object(llm, "Groq") as groq_class, patch.object(
            llm.httpx, "Client"
        ):
            client = groq_class.return_value
            client.chat.completions.create.side_effect = RuntimeError("unavailable")

            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                llm.ask([], [])

            client.close.assert_called_once()