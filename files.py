"""
files.py — Read files from disk for the claude-shrink MCP server.

Responsibilities:
- Resolve relative paths against os.getcwd()
- Validate files exist and are readable
- Detect and skip binary files
- Enforce per-file (100KB) and total (500KB) size caps
- Return structured results with clear error messages
"""

import os
from pathlib import Path

# Size limits
MAX_FILE_SIZE_BYTES = 100 * 1024       # 100 KB per file
MAX_TOTAL_SIZE_BYTES = 500 * 1024      # 500 KB combined


class TooLargeError(Exception):
    """Raised when combined file contents exceed MAX_TOTAL_SIZE_BYTES."""

    def __init__(self, total_bytes: int, file_count: int):
        self.total_bytes = total_bytes
        self.file_count = file_count
        super().__init__(
            f"Combined file size ({total_bytes:,} bytes across {file_count} files) "
            f"exceeds the {MAX_TOTAL_SIZE_BYTES:,} byte limit. "
            f"Try passing fewer files, or split the request into smaller chunks."
        )


def _is_binary(data: bytes) -> bool:
    """Detect binary files by checking for null bytes in the first 8KB."""
    return b"\x00" in data[:8192]


def _resolve_path(path_str: str) -> Path:
    """Resolve a path string to an absolute Path.

    Relative paths are resolved against os.getcwd(), which for an MCP
    server subprocess is typically the directory where Claude Code was
    invoked.
    """
    p = Path(path_str)
    if not p.is_absolute():
        p = Path(os.getcwd()) / p
    return p.resolve()


def read_files(paths: list[str]) -> list[dict]:
    """Read a list of file paths and return structured results.

    Each result dict has:
        path:    str  — the absolute path that was tried
        content: str | None — file contents if successfully read
        skipped: bool — True if the file was skipped
        reason:  str | None — why it was skipped (if skipped)

    Raises:
        TooLargeError: if combined readable content exceeds MAX_TOTAL_SIZE_BYTES

    Files that don't exist, aren't readable, are binary, or exceed the
    per-file size limit are skipped individually with a reason — the call
    does not fail for the remaining files.
    """
    results: list[dict] = []
    total_bytes = 0

    for path_str in paths:
        abs_path = _resolve_path(path_str)
        entry: dict = {
            "path": str(abs_path),
            "content": None,
            "skipped": False,
            "reason": None,
        }

        # --- Check existence ---
        if not abs_path.exists():
            entry["skipped"] = True
            entry["reason"] = f"File not found: {abs_path} — check the path and try again."
            results.append(entry)
            continue

        if not abs_path.is_file():
            entry["skipped"] = True
            entry["reason"] = f"Not a file (may be a directory): {abs_path}"
            results.append(entry)
            continue

        # --- Check readable ---
        try:
            raw = abs_path.read_bytes()
        except PermissionError:
            entry["skipped"] = True
            entry["reason"] = f"Permission denied: {abs_path}"
            results.append(entry)
            continue
        except OSError as e:
            entry["skipped"] = True
            entry["reason"] = f"Could not read {abs_path}: {e}"
            results.append(entry)
            continue

        # --- Check binary ---
        if _is_binary(raw):
            entry["skipped"] = True
            entry["reason"] = f"Binary file skipped: {abs_path}"
            results.append(entry)
            continue

        # --- Check per-file size ---
        if len(raw) > MAX_FILE_SIZE_BYTES:
            entry["skipped"] = True
            entry["reason"] = (
                f"File too large ({len(raw):,} bytes, limit is "
                f"{MAX_FILE_SIZE_BYTES:,} bytes): {abs_path}"
            )
            results.append(entry)
            continue

        # --- Check total size ---
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_SIZE_BYTES:
            raise TooLargeError(total_bytes, len(results) + 1)

        # --- Decode ---
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("latin-1")
            except UnicodeDecodeError:
                entry["skipped"] = True
                entry["reason"] = f"Could not decode file (not UTF-8 or Latin-1): {abs_path}"
                results.append(entry)
                continue

        entry["content"] = text
        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Manual smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    test_paths = sys.argv[1:] if len(sys.argv) > 1 else [__file__]
    print(f"Testing read_files with: {test_paths}\n")

    try:
        results = read_files(test_paths)
    except TooLargeError as e:
        print(f"TooLargeError: {e}")
        sys.exit(1)

    for r in results:
        if r["skipped"]:
            print(f"SKIPPED  {r['path']}")
            print(f"  Reason: {r['reason']}")
        else:
            lines = r["content"].count("\n") + 1
            size = len(r["content"].encode("utf-8"))
            print(f"OK       {r['path']}  ({lines} lines, {size:,} bytes)")

    print(f"\nTotal files: {len(results)}")
    print(f"Read: {sum(1 for r in results if not r['skipped'])}")
    print(f"Skipped: {sum(1 for r in results if r['skipped'])}")
