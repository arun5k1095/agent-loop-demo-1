"""Tool definitions the model can see, plus the code that actually runs them.

The model never runs code. It only *asks* for a tool by name with JSON
arguments; run_tool() is where we turn that request into a real HTTP call.
"""

import requests

TOOL_SERVER_URL = "http://localhost:5000"
TIMEOUT_SECONDS = 10

# Sent to the model on every call. The JSON schema tells it which arguments to produce.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city: temperature in Celsius and a short description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. 'London' or 'Paris,FR'."},
                },
                "required": ["city"],
            },
        },
    },
]


def get_weather(args: dict) -> str:
    """Handler for the get_weather tool: GET /weather on the Flask server."""
    try:
        response = requests.get(f"{TOOL_SERVER_URL}/weather", params={"city": args.get("city")}, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return f"error: could not reach the tool server at {TOOL_SERVER_URL} ({type(exc).__name__}). Is tool_server/app.py running?"
    # The server validates the city and replies with JSON either way (an "error" key on failure), so pass it through as-is.
    return response.text


# tool name (as the model sees it) -> Python function that runs it. Also the allowlist of what the model may run.
TOOL_HANDLERS = {"get_weather": get_weather}


def run_tool(name: str, args: dict) -> str:
    """Run the named tool and return its result as text for the model.

    Errors are returned as strings on purpose: the model can read them and
    recover (retry, ask the user, explain), which it cannot do if we raise.
    """
    if name not in TOOL_HANDLERS:
        return f"error: unknown tool '{name}'"
    return TOOL_HANDLERS[name](args)
