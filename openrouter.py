"""
openrouter.py — OpenRouter client for claude-shrink.

Calls Kimi K2.6 via OpenRouter's OpenAI-compatible API.
Same return shape as cloudflare.py: {summary, input_tokens, output_tokens}
"""

import os
import asyncio
import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"
# Verify this model ID at openrouter.ai/models before launch
OPENROUTER_MODEL = "moonshotai/kimi-k2.6"


class OpenRouterError(Exception):
    def __init__(self, status: int, body: str, user_message: str):
        self.status = status
        self.body = body
        self.user_message = user_message
        super().__init__(user_message)


def _get_api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise OpenRouterError(
            0, "",
            "OPENROUTER_API_KEY is not set. Add it to your .env file. "
            "Get a key at openrouter.ai/keys, then add credits at openrouter.ai/credits."
        )
    return key


def _handle_error(status: int, body: str) -> None:
    if status in (401, 403):
        raise OpenRouterError(
            status, body,
            "Invalid OpenRouter API key. Check OPENROUTER_API_KEY in your .env file. "
            "Generate a new one at openrouter.ai/keys."
        )
    if status == 429:
        raise OpenRouterError(
            status, body,
            "OpenRouter rate limit hit. Wait a moment and retry, "
            "or add credits at openrouter.ai/credits."
        )
    raise OpenRouterError(
        status, body,
        f"OpenRouter API error (HTTP {status}). Response: {body[:500]}"
    )


async def call_kimi(system_prompt: str, user_prompt: str) -> dict:
    """Call Kimi K2.6 via OpenRouter.

    Returns:
        {"summary": str, "input_tokens": int, "output_tokens": int}
    """
    api_key = _get_api_key()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # OpenRouter asks for these for app identification
        "HTTP-Referer": "https://github.com/aghori3004/claude-shrink",
        "X-Title": "claude-shrink",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 8000,
    }

    last_status = 0
    last_body = ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(2):
            try:
                resp = await client.post(OPENROUTER_BASE, headers=headers, json=payload)
            except httpx.HTTPError as e:
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                raise OpenRouterError(0, str(e), f"Network error calling OpenRouter: {e}")

            last_status = resp.status_code
            last_body = resp.text

            if last_status in (401, 403, 429):
                _handle_error(last_status, last_body)

            if last_status >= 500:
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                _handle_error(last_status, last_body)

            if 200 <= last_status < 300:
                break

            _handle_error(last_status, last_body)

    data = resp.json()

    # Standard OpenAI response shape
    try:
        summary = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise OpenRouterError(
            last_status, last_body,
            f"Could not parse OpenRouter response. Keys present: {list(data.keys())}"
        )

    if not summary:
        raise OpenRouterError(last_status, last_body, "OpenRouter returned empty summary.")

    usage = data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    # Fallback if usage not reported
    if input_tokens == 0:
        input_tokens = len(user_prompt) // 4 + len(system_prompt) // 4
    if output_tokens == 0:
        output_tokens = len(summary) // 4

    return {
        "summary": summary,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
