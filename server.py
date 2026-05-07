"""
server.py — Claude Shrink MCP server.

Exposes one tool: read_and_summarize_files
Reads files from disk, sends them to Kimi K2.6 via the configured provider,
and returns a task-shaped summary to Claude's context window.
"""

import os
import time

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

from mcp.server.fastmcp import FastMCP

from tool_description import TOOL_DESCRIPTION
from files import read_files, TooLargeError
from logger import log_call

_has_openrouter = bool(os.getenv("OPENROUTER_API_KEY"))
_has_cloudflare = bool(os.getenv("CF_ACCOUNT_ID")) and bool(os.getenv("CF_API_TOKEN"))

if _has_openrouter:
    from openrouter import call_kimi, OpenRouterError as ProviderError
elif _has_cloudflare:
    from cloudflare import call_kimi, CloudflareError as ProviderError
else:
    raise RuntimeError(
        "No provider credentials found. "
        "Set OPENROUTER_API_KEY for OpenRouter, "
        "or set both CF_ACCOUNT_ID and CF_API_TOKEN for Cloudflare Workers AI."
    )

# ---------------------------------------------------------------------------
# Kimi prompt templates
# ---------------------------------------------------------------------------

_DEPTH_RULES = {
    "concise": (
        "Focus only on what is directly relevant to the user's task. "
        "Cut everything else ruthlessly. Never cut substance."
    ),
    "thorough": (
        "Cover all major components, patterns, data flows, and design decisions. "
        "Include: file responsibilities, key types/classes/functions and their "
        "signatures, important state, error handling patterns, inter-file "
        "dependencies. Be comprehensive — the user needs a full mental model."
    ),
}

_KIMI_SYSTEM_BASE = """\
You are summarizing source files for an AI coding assistant (Claude) \
working on a specific user task. Your summary replaces the raw files \
in Claude's context window. Claude needs enough detail to answer the \
task without re-reading any of these files.

Rules:
- {depth_rule}
- Order content by relevance to the task. Most important first.
- Keep real function names, key parameter signatures, important \
branches, error paths. Do not paraphrase code structure into \
vague descriptions.
- Skip files not relevant to the task. List them in one line at end.
- No filler phrases like "this codebase is well-organized."
- Format: file path as a header, then bullet points underneath.\
"""


def _build_system_prompt(depth: str) -> str:
    rule = _DEPTH_RULES.get(depth, _DEPTH_RULES["concise"])
    return _KIMI_SYSTEM_BASE.format(depth_rule=rule)

KIMI_USER_TEMPLATE = """\
The user is currently trying to do this:

{user_task}

Here are the files. Summarize them according to the rules.

{file_blocks}\
"""

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("claude-shrink")


@mcp.tool(description=TOOL_DESCRIPTION)
async def read_and_summarize_files(
    paths: list[str],
    user_task: str,
    depth: str = "concise",
) -> str:
    """Read files and return a task-shaped summary via Kimi K2.6.

    Args:
        paths: File paths to read and summarize. Absolute or repo-relative.
        user_task: What the user is currently trying to do. The summary
                   will be shaped to give Claude what it needs to answer
                   this task without re-reading the files. Be specific.
        depth: "concise" (default) for targeted questions, "thorough" for
               broad overviews and architecture explanations.
    """
    # ---- 1. Read files from disk ----
    try:
        results = read_files(paths)
    except TooLargeError as e:
        return str(e)

    # Collect readable files
    readable = [r for r in results if not r["skipped"]]
    skipped = [r for r in results if r["skipped"]]

    if not readable:
        # All files were skipped — return reasons
        lines = ["No files could be read. Details:"]
        for s in skipped:
            lines.append(f"  - {s['reason']}")
        return "\n".join(lines)

    # ---- 2. Build prompt ----
    file_blocks = []
    total_chars = 0
    for r in readable:
        block = f"=== {r['path']} ===\n{r['content']}"
        file_blocks.append(block)
        total_chars += len(r["content"])

    user_prompt = KIMI_USER_TEMPLATE.format(
        user_task=user_task,
        file_blocks="\n\n".join(file_blocks),
    )

    # ---- 3. Call Kimi ----
    start_time = time.time()
    try:
        system_prompt = _build_system_prompt(depth)
        kimi_result = await call_kimi(system_prompt, user_prompt)
    except ProviderError as e:
        return e.user_message
    wall_time = time.time() - start_time

    summary = kimi_result["summary"]

    # ---- 4. Log the call ----
    try:
        log_call(
            files_read=len(readable),
            input_chars=total_chars,
            kimi_input_tokens=kimi_result["input_tokens"],
            kimi_output_tokens=kimi_result["output_tokens"],
            user_task=user_task,
            wall_time_seconds=wall_time,
        )
    except Exception:
        pass  # Logging failure should never break the tool

    # ---- 5. Build response ----
    parts = [summary]

    if skipped:
        skip_lines = [f"\n---\nFiles we couldn't read:"]
        for s in skipped:
            skip_lines.append(f"  - {s['reason']}")
        parts.append("\n".join(skip_lines))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
