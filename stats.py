"""
stats.py — CLI that reads log.jsonl and prints usage stats.

Usage:
    python stats.py

Prints daily, weekly, and all-time stats with three-tier cost estimates,
plus the last 5 calls. Backwards-compatible with old log entries that
lack the new fields.
"""

import time
from datetime import datetime
from logger import read_log


def _format_tokens(n: int) -> str:
    """Format token count with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _format_cost(usd: float) -> str:
    """Format USD cost."""
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.3f}"


def _format_ts(ts: int) -> str:
    """Format a Unix timestamp to a human-readable local time string."""
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


def _get(entry: dict, key: str, default=0):
    """Get a value from an entry with a default, for backwards compat."""
    return entry.get(key, default)


def _print_period(label: str, entries: list[dict]) -> None:
    """Print aggregated stats for a time period."""
    if not entries:
        print(f"  {label}: no calls")
        return

    calls = len(entries)
    files = sum(_get(e, "files_read") for e in entries)
    tokens_avoided = sum(
        _get(e, "main_context_tokens_avoided",
             _get(e, "main_context_tokens_saved"))
        for e in entries
    )
    explore_count = sum(1 for e in entries if _get(e, "explore_likely_triggered", False))

    cost_conservative = sum(_get(e, "cost_avoided_conservative_usd") for e in entries)
    cost_likely = sum(_get(e, "cost_avoided_likely_usd",
                           _get(e, "estimated_sonnet_cost_usd_avoided")) for e in entries)
    cost_best = sum(_get(e, "cost_avoided_best_case_usd") for e in entries)

    print(f"  {label}:")
    print(f"    Calls:                   {calls}")
    print(f"    Files summarized:        {files}")
    print(f"    Tokens kept out of main: {_format_tokens(tokens_avoided)}")
    print(f"    Likely Explore avoids:   {explore_count}")
    print()
    print(f"    Cost avoided (Sonnet equivalent):")
    print(f"      Conservative:  {_format_cost(cost_conservative)}")
    print(f"      Likely:        {_format_cost(cost_likely)}")
    print(f"      Best case:     {_format_cost(cost_best)}")


def main():
    entries = read_log()

    if not entries:
        print("No calls logged yet.")
        return

    today_start = int(datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp())
    week_start = today_start - (7 * 24 * 60 * 60)

    today_entries = [e for e in entries if _get(e, "ts") >= today_start]
    week_entries = [e for e in entries if _get(e, "ts") >= week_start]

    print()
    print("=" * 50)
    print("  claude-shrink usage stats")
    print("=" * 50)
    print()

    _print_period("Today", today_entries)
    print()
    _print_period("This week", week_entries)
    print()
    _print_period("All time", entries)

    # Last 5 calls
    print()
    print("  Last 5 calls:")
    recent = entries[-5:]
    for e in reversed(recent):
        ts_str = _format_ts(_get(e, "ts"))
        files = _get(e, "files_read")
        tokens = _format_tokens(
            _get(e, "main_context_tokens_avoided",
                 _get(e, "main_context_tokens_saved"))
        )
        explore = _get(e, "explore_likely_triggered", False)
        explore_str = "Explore-likely" if explore else ""

        # Show best-case cost if explore likely, otherwise likely cost
        if explore:
            cost = _get(e, "cost_avoided_best_case_usd")
            cost_label = "best"
        else:
            cost = _get(e, "cost_avoided_likely_usd",
                        _get(e, "estimated_sonnet_cost_usd_avoided"))
            cost_label = "likely"

        parts = [
            f"    {ts_str}",
            f"{files:>2} files",
            f"{tokens:>6} tokens",
            f"{explore_str:<14}" if explore_str else f"{'':14}",
            f"{_format_cost(cost)} {cost_label}",
        ]
        print(" | ".join(parts))

    print()


if __name__ == "__main__":
    main()
