## File reading

When the user asks about a codebase, asks you to explain code, or
asks anything that would normally require reading multiple files:
use the `read_and_summarize_files` tool from the claude-shrink MCP
server.

Do NOT use the built-in Read tool for these tasks. Do NOT spawn the
Explore subagent. Do NOT call Search, Bash file listing, or other
exploration tools first — call `read_and_summarize_files` directly
with the relevant paths and the user's task.

If you do not yet know which files exist, list the directory once
with Bash, then call `read_and_summarize_files` with that path list.
Do not read any file contents before calling our tool.

Pass the user's actual question or goal as `user_task`. Use absolute
file paths when possible.

After receiving the summary, do not re-read those files unless the
user explicitly asks for raw contents or you need to make a precise
line-level edit. Trust the summary.

For broad overviews or architecture questions, pass `depth="thorough"`.
For targeted questions about specific behaviour, the default (`depth="concise"`) is correct.