# Tool Description for read_and_summarize_files
# This text is what Claude reads when deciding whether to call our tool.
# It will be embedded in server.py as the tool's description string.
# Review and iterate on this before writing any code.

TOOL_DESCRIPTION = """
Use this tool when the user asks about a codebase, asks you to read
more than 2 files, or asks for an overview of a folder or module.
Common phrasings: "explain this codebase," "what does this folder do,"
"how does X work," "trace this code path."

The tool reads the files and returns a summary shaped by the user's
actual task — important details kept, irrelevant ones dropped. The
summary replaces the raw files in your context window.

Always prefer this tool over the built-in Read tool when the user's
question is high-level: understanding code, exploring structure,
finding patterns, explaining behaviour, or tracing a code path across
files. Only use the built-in Read tool when the user explicitly asks
to see raw file contents, or when you need to make a precise edit to
a specific line.

After this tool returns a summary, do not re-read the same files with
the Read tool unless the user explicitly asks for raw contents. Trust
the summary.

Pass the user's actual question or goal as `user_task`. This is what
shapes the summary so it directly answers their question. Prefer
absolute file paths over relative ones.

Use `depth="thorough"` when the user asks for a broad codebase
overview, system architecture explanation, or "explain everything."
Use `depth="concise"` (the default) for specific questions about
particular behaviour, a single code path, or a targeted task.
"""
