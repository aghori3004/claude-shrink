"""
cloudflare.py — Cloudflare Workers AI client for claude-shrink.

Calls Kimi K2.6 via the Cloudflare Workers AI REST API.
Handles auth errors (401/403), rate limits (429), and transient 5xx
with one retry after 2 seconds.
"""

import os
import asyncio
import httpx
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

MODEL_ID = "@cf/moonshotai/kimi-k2.6"
MAX_TOKENS_KEY = "max_tokens"  # Switch to "max_completion_tokens" if deprecation detected


class CloudflareError(Exception):
    """Raised on non-retryable Cloudflare API errors."""

    def __init__(self, status: int, body: str, user_message: str):
        self.status = status
        self.body = body
        self.user_message = user_message
        super().__init__(user_message)


def _get_credentials() -> tuple[str, str]:
    """Load and validate Cloudflare credentials from environment."""
    account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CF_API_TOKEN", "").strip()

    if not account_id:
        raise CloudflareError(
            0, "",
            "CF_ACCOUNT_ID is not set. Add it to your .env file. "
            "Find it at dash.cloudflare.com > Workers AI (top of the page)."
        )
    if not api_token:
        raise CloudflareError(
            0, "",
            "CF_API_TOKEN is not set. Add it to your .env file. "
            "Create a token at dash.cloudflare.com > My Profile > API Tokens."
        )

    return account_id, api_token


def _handle_error(status: int, body: str) -> None:
    """Raise CloudflareError with a human-readable message for known error codes."""
    if status in (401, 403):
        raise CloudflareError(
            status, body,
            "Invalid Cloudflare API token. Open your .env file and check that "
            "CF_API_TOKEN is correct. You can create a new token at "
            "dash.cloudflare.com > My Profile > API Tokens."
        )
    if status == 429:
        raise CloudflareError(
            status, body,
            "Cloudflare free tier limit reached for today. Your quota resets "
            "daily. Wait until tomorrow or upgrade your Cloudflare Workers AI plan."
        )
    raise CloudflareError(
        status, body,
        f"Cloudflare API error (HTTP {status}). Response: {body[:500]}"
    )


async def call_kimi(system_prompt: str, user_prompt: str) -> dict:
    """Call Kimi K2.6 via Cloudflare Workers AI.

    Args:
        system_prompt: The system instructions for Kimi.
        user_prompt: The user message containing file contents + task.

    Returns:
        {
            "summary": str,        # The model's response text
            "input_tokens": int,   # Tokens consumed by the prompt
            "output_tokens": int,  # Tokens in the response
        }

    Raises:
        CloudflareError: On auth failure, rate limit, or persistent API error.
    """
    account_id, api_token = _get_credentials()

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/ai/run/{MODEL_ID}"
    )
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        MAX_TOKENS_KEY: 8000,
    }

    last_status = 0
    last_body = ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(2):  # 1 initial + 1 retry on 5xx
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                raise CloudflareError(0, str(e), f"Network error calling Cloudflare: {e}")

            last_status = resp.status_code
            last_body = resp.text

            # Non-retryable errors — raise immediately
            if last_status in (401, 403, 429):
                _handle_error(last_status, last_body)

            # 5xx — retry once
            if last_status >= 500:
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                _handle_error(last_status, last_body)

            # Success
            if 200 <= last_status < 300:
                break

            # Any other error
            _handle_error(last_status, last_body)

    # Parse response
    data = resp.json()

    # Cloudflare Workers AI wraps the result in {"result": {...}, "success": true}
    result = data.get("result", data)

    # Extract the response text
    summary = ""
    if isinstance(result, dict):
        # Standard chat completion shape
        if "response" in result:
            summary = result["response"]
        elif "choices" in result:
            choices = result["choices"]
            if choices and isinstance(choices[0], dict):
                msg = choices[0].get("message", {})
                summary = msg.get("content", "")
    elif isinstance(result, str):
        summary = result

    if not summary:
        raise CloudflareError(
            last_status, last_body,
            f"Could not extract summary from Cloudflare response. "
            f"Raw response shape: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
        )

    # Extract token usage if available
    usage = data.get("usage", {})
    if not usage and isinstance(result, dict):
        usage = result.get("usage", {})

    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    # Approximate fallback: if Cloudflare returns 0 for usage, estimate
    # from character counts (chars / 4 ≈ tokens). This is a rough heuristic
    # but keeps logging and stats directionally useful.
    if input_tokens == 0:
        input_tokens = len(user_prompt) // 4 + len(system_prompt) // 4
    if output_tokens == 0:
        output_tokens = len(summary) // 4

    # Check for deprecation warnings in the response
    # If Cloudflare flags max_tokens as deprecated, this will help us detect it
    if isinstance(data, dict):
        warnings = data.get("warnings", [])
        if warnings:
            print(f"[claude-shrink] Cloudflare API warnings: {warnings}")

    return {
        "summary": summary,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


# ---------------------------------------------------------------------------
# Throwaway test — run directly to verify the API works
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Cloudflare Workers AI — Kimi K2.6 throwaway test")
    print("=" * 60)
    print(f"Model: {MODEL_ID}")
    print(f"Token key: {MAX_TOKENS_KEY}")
    print()

    test_system = "You are a helpful assistant. Respond concisely."
    test_user = (
        "Summarize what this Python function does in 2 bullet points:\n\n"
        "def fibonacci(n):\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fibonacci(n-1) + fibonacci(n-2)\n"
    )

    async def run_test():
        try:
            result = await call_kimi(test_system, test_user)
            print("SUCCESS\n")
            print(f"Summary:\n{result['summary']}\n")
            print(f"Input tokens:  {result['input_tokens']}")
            print(f"Output tokens: {result['output_tokens']}")
            print()

            if result['input_tokens'] == 0:
                print("[NOTE] Token counts returned as 0 — Cloudflare may not "
                      "report usage for this model. Logging will use 0.")

        except CloudflareError as e:
            print(f"FAILED — {e.user_message}")
            if e.body:
                print(f"Raw response: {e.body[:500]}")
            sys.exit(1)

    asyncio.run(run_test())
