"""
logger.py — Append-only JSONL logging for claude-shrink.

Each call to read_and_summarize_files gets logged as one JSON line
in log.jsonl. No database, no telemetry sent anywhere.

Logs a cost range (conservative / likely / best case) instead of a
single number, since the true counterfactual is unknowable. Also
detects when Claude's Explore subagent would likely have fired.
"""

import time
import json
from pathlib import Path

LOG_FILE = Path(__file__).parent / "log.jsonl"

# Cost constants (Sonnet 4.6 pricing, May 2026)
SONNET_INPUT_RATE = 3.0 / 1_000_000        # $3/M fresh input
SONNET_CACHE_READ_RATE = 0.30 / 1_000_000  # $0.30/M cache read
BLENDED_RATE = 5.0 / 1_000_000             # ~$5/M effective in multi-turn sessions

# Empirical: from A/B test, Explore subagent runs cost ~$0.06-0.10 per fire
EXPLORE_AVOIDANCE_CONST = 0.07

EXPLORE_KEYWORDS = (
    "explain", "overview", "understand", "trace",
    "how does", "architecture", "walk me through",
    "what does this", "describe the",
)


def estimate_explore_likely(files_read: int, user_task: str) -> bool:
    """Heuristic: would Claude likely have spawned the Explore subagent?"""
    if files_read < 5:
        return False
    task = user_task.lower()
    return any(kw in task for kw in EXPLORE_KEYWORDS)


def log_call(
    files_read: int,
    input_chars: int,
    kimi_input_tokens: int,
    kimi_output_tokens: int,
    user_task: str = "",
    wall_time_seconds: float = 0.0,
) -> None:
    """Append one call record to log.jsonl.

    Logs a cost range instead of a single number because the true
    counterfactual (what Claude would have spent without our tool)
    is unknowable. The three tiers:
      - Conservative: avoided tokens priced at cache-read rate ($0.30/M)
      - Likely: avoided tokens at blended multi-turn rate (~$5/M)
      - Best case: likely + Explore subagent avoidance if applicable
    """
    # Approximate: chars/4 ≈ tokens for the raw file content
    file_content_tokens = input_chars // 4
    main_context_tokens_avoided = max(0, file_content_tokens - kimi_output_tokens)

    cost_conservative = main_context_tokens_avoided * SONNET_CACHE_READ_RATE
    cost_likely = main_context_tokens_avoided * BLENDED_RATE

    explore_likely = estimate_explore_likely(files_read, user_task)
    cost_best_case = cost_likely + (EXPLORE_AVOIDANCE_CONST if explore_likely else 0)

    entry = {
        "ts": int(time.time()),
        "files_read": files_read,
        "input_chars": input_chars,
        "file_content_tokens": file_content_tokens,
        "kimi_input_tokens": kimi_input_tokens,
        "kimi_output_tokens": kimi_output_tokens,
        "main_context_tokens_avoided": main_context_tokens_avoided,
        "explore_likely_triggered": explore_likely,
        "cost_avoided_conservative_usd": round(cost_conservative, 6),
        "cost_avoided_likely_usd": round(cost_likely, 6),
        "cost_avoided_best_case_usd": round(cost_best_case, 6),
        "user_task_preview": user_task[:80],
        "wall_time_seconds": round(wall_time_seconds, 2),
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def read_log() -> list[dict]:
    """Read all entries from log.jsonl.

    Returns an empty list if the file does not exist or is empty.
    """
    if not LOG_FILE.exists():
        return []

    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # Skip malformed lines
    return entries
