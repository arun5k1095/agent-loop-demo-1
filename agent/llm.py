"""The only file that talks to the LLM provider (Groq).

Groq speaks the OpenAI chat-completions format, so swapping to another
OpenAI-compatible provider mostly means changing the client and MODEL here.
"""

import ssl

import httpx
import truststore
from groq import Groq
from groq.types.chat import ChatCompletionMessage

from config import load_secrets

MODEL = "openai/gpt-oss-120b"  # must be a Groq model that supports tool use


def ask(messages: list[dict], tools: list[dict]) -> ChatCompletionMessage:
    """Send the whole conversation plus the tool list to the model, once.

    Returns the model's reply message: either plain text in .content
    (a final answer) or one or more requests in .tool_calls.

    Non-streaming on purpose: a streamed tool call arrives in fragments that
    would have to be stitched back together, which would hide the lesson.
    """

    secrets = load_secrets()
    api_key = secrets["GROQ_API_KEY"]
    tls_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client = Groq(
        api_key=api_key,
        timeout=60.0,
        max_retries=2,
        http_client=httpx.Client(verify=tls_context),
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_completion_tokens=2000,
        )
        reply = response.choices[0].message
        return reply
    finally:
        client.close()
