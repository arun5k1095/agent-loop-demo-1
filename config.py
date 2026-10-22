"""Read API keys directly from the local, gitignored secrets.json file."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_secrets() -> dict[str, str]:
    """Read keys from JSON; file and parsing errors propagate to the caller.

    Raise RuntimeError if the JSON object does not contain valid API keys.
    """
    secrets_file = ROOT / "secrets.json"
    secrets = json.loads(secrets_file.read_text(encoding="utf-8"))
    if not isinstance(secrets, dict):
        raise RuntimeError("secrets.json must contain a JSON object.")
    for name in ("GROQ_API_KEY", "OPENWEATHER_API_KEY"):
        value = secrets.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Set a non-empty {name} string in secrets.json.")
    return secrets
