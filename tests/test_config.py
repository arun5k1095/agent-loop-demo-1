import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config


class ConfigurationTests(unittest.TestCase):
    def test_reads_json_without_using_or_changing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = {"GROQ_API_KEY": "test-groq-value", "OPENWEATHER_API_KEY": "test-weather-value"}
            (root / "secrets.json").write_text(json.dumps(expected), encoding="utf-8")
            with patch.object(config, "ROOT", root), patch.dict(os.environ, {"GROQ_API_KEY": "ignored-environment-value"}):
                self.assertEqual(config.load_secrets(), expected)
                self.assertEqual(os.environ["GROQ_API_KEY"], "ignored-environment-value")

    def test_invalid_configuration_is_rejected(self):
        invalid_values = ["[]", "{}", '{"GROQ_API_KEY": 123}', '{"GROQ_API_KEY": " "}']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(config, "ROOT", root):
                with self.assertRaises(FileNotFoundError):
                    config.load_secrets()
                (root / "secrets.json").write_text("{", encoding="utf-8")
                with self.assertRaises(json.JSONDecodeError):
                    config.load_secrets()
                for text in invalid_values:
                    with self.subTest(text=text):
                        (root / "secrets.json").write_text(text, encoding="utf-8")
                        with self.assertRaises(RuntimeError):
                            config.load_secrets()