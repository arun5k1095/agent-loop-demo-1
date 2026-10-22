"""Flask UI server: a small web page in front of the agent loop.

Run from the project root:  python ui_server/app.py   then open http://127.0.0.1:8000
The tool server (tool_server/app.py) must be running too, or the weather tool will fail.
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from groq import APIConnectionError, APIStatusError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # lets this script import config.py and agent/ from the project root

from agent.loop import run_agent

app = Flask(__name__)  # serves templates/index.html at "/" and the files in static/ at "/static/..."


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/ask")
def ask_endpoint():
    """POST /ask {"question": "..."} -> {"answer": "...", "steps": ["[step 1] ...", "[tool result] ...", ...]}"""
    body = request.get_json(silent=True)  # None when the request body is not JSON
    question = body.get("question") if isinstance(body, dict) else None
    if not isinstance(question, str) or not question.strip() or len(question) > 500:
        return jsonify(error="'question' must be a non-empty string (max 500 characters)"), 400

    steps = []

    def remember(line):
        print(line)  # same trace you see when running loop.py in a terminal
        steps.append(line)  # plus a copy for the browser

    try:
        answer = run_agent(question.strip(), log=remember)
    except APIConnectionError:
        app.logger.warning("Groq connection failed")
        return jsonify(error="Could not connect to the AI provider. Check network access and trusted certificates, then restart the UI server.", steps=steps), 503
    except APIStatusError as error:
        app.logger.warning("Groq request failed with status %s", error.status_code)
        return jsonify(error="The AI provider rejected the request. Check API credentials, model access, and usage limits.", steps=steps), 502
    return jsonify(answer=answer, steps=steps)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)  # local only
