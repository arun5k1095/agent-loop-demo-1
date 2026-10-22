"""The agent loop, written by hand.

    question -> LLM -> (tool requested? run it, feed the result back, repeat) -> final answer

Run from the project root:  python agent/loop.py "What's the weather in Paris?"
"""

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # lets this script import config.py from the project root

from agent.llm import ask
from agent.tools import TOOLS, run_tool

SYSTEM_PROMPT = (
    "You are a concise assistant. When asked about the weather, always call the "
    "get_weather tool instead of guessing, then answer in one or two sentences."
)


def run_agent(question: str, max_steps: int = 5, log=print) -> Optional[str]:
    """Run the loop until the model answers in plain text or max_steps is reached.

    log is called with one line per event. The default prints to the terminal;
    ui_server/app.py passes a function that also collects the lines for the browser.
    """
    # The conversation is just a list of messages. Everything the model knows is in here.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for step in range(1, max_steps + 1):
        # 1. Ask the model what to do next, given the whole conversation so far.
        reply = ask(messages, TOOLS)

        # 2. No tool call means the model is done: its text is the final answer.
        tool_calls = reply.tool_calls  # None (not an empty list) when the model answered in plain text
        if tool_calls is None or len(tool_calls) == 0:
            log(f"[final answer] {reply.content}")
            return reply.content

        # 3. Keep the model's own tool request in the history, in the shape the API expects back.
        messages.append(
            {
                "role": "assistant",
                "content": reply.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                    for call in tool_calls
                ],
            }
        )

        # 4. Run each requested tool and append its result as a "tool" message.
        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}  # run_tool will report the missing argument back to the model
            pretty_args = ", ".join(f"{key}={value}" for key, value in args.items())
            log(f"[step {step}] LLM requested {name}({pretty_args})")

            result = run_tool(name, args)
            log(f"[tool result] {result}")
            messages.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": result})

        # 5. Back to the top: the next ask() sees the tool results and can answer or ask for more.

    log(f"[stopped] no final answer after {max_steps} steps")
    return None


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What's the weather in London?"
    run_agent(question)
