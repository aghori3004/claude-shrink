# claude-shrink

**Cuts Claude Code's file-reading token cost by ~46%. One MCP tool. 60-second install.**

When you ask Claude "explain this codebase," it opens 10–20 files directly into its
context window — and burns your weekly Pro/Max limit on reads, not reasoning.
claude-shrink intercepts those reads, sends the files to Kimi K2.6 (via OpenRouter),
and returns a task-shaped summary. Claude's context grows by ~500 tokens instead of ~40,000.

In an A/B test across 4 prompts on a real codebase:
- **Total session cost: $0.28 with claude-shrink vs $0.52 without (-46%)**
- The entire difference came from the Explore subagent ($0.0004 vs $0.25)
- No quality loss on specific questions; mild depth reduction on broad overviews
  (now fixed with the `depth` parameter)

---

## How it works

```
You → Claude Code → read_and_summarize_files (MCP tool)
                         ↓
                    Read files from disk
                         ↓
                    Send to Kimi K2.6 (OpenRouter, free tier)
                         ↓
                    Return task-shaped summary to Claude
```

Claude continues with the summary in context. It never sees the raw files.
Quality stays high because Claude handles all reasoning — only the
"read and understand files" step is delegated.

---

## Install

### 1. Clone the repo

```bash
git clone https://github.com/divyaaa-13/claude-shrink.git
cd claude-shrink
python3 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Get an OpenRouter API key

Go to **[openrouter.ai/keys](https://openrouter.ai/keys)** → Create key.
No credit card required. Free tier covers normal usage. Takes 30 seconds.

### 3. Configure

```bash
cp .env.example .env
```

Open `.env` and paste your key:
```
OPENROUTER_API_KEY=sk-or-...
```

### 4. Register with Claude Code

```bash
claude mcp add claude-shrink python /full/path/to/claude-shrink/server.py
```

Replace `/full/path/to/` with the actual path where you cloned the repo.

### 5. Add to your project's CLAUDE.md

Paste the contents of `CLAUDE.md.snippet` into your project's `CLAUDE.md`.

### 6. Verify

Start a new Claude Code session. Ask: "Explain the files in this folder."
Claude should call `read_and_summarize_files` instead of opening files directly.

---

## Check your savings

```bash
python stats.py
```

Shows daily, weekly, and all-time stats with three-tier cost estimates
(conservative / likely / best case) plus the last 5 calls.

---

## Depth parameter

The tool accepts a `depth` parameter that shapes how detailed the summary is:

| Value | When to use | What it does |
|-------|-------------|--------------|
| `"concise"` (default) | Specific questions, single code paths | Keeps only what's relevant to the task |
| `"thorough"` | "Explain this codebase", architecture overviews | Covers all components, patterns, data flows, and design decisions |

Claude picks the right depth automatically based on the tool description.

---

## Alternative: Cloudflare Workers AI

By default, claude-shrink uses **OpenRouter** (recommended — simpler setup, no daily cap).

To use **Cloudflare Workers AI** instead:

1. Set `PROVIDER=cloudflare` in your `.env`
2. Uncomment and fill in `CF_ACCOUNT_ID` and `CF_API_TOKEN`

**Getting Cloudflare credentials:**

1. Sign up at [dash.cloudflare.com](https://dash.cloudflare.com) (free, no credit card)
2. Go to **AI → Workers AI** in the sidebar and accept terms of service
3. Copy your **Account ID** (shown at the top of the Workers AI page)
4. Create an **API Token:** My Profile → API Tokens → Create Token → Custom token → Account → Workers AI → Read

> **Note:** Cloudflare's free tier has a 10,000 neuron/day cap (~2–5M tokens).
> For most developers this is plenty, but heavy usage may hit the limit.

---

## Known limits

- **One model:** Kimi K2.6 via either OpenRouter or Cloudflare. No model selection in V1.
- **Text files only:** Binary files (images, PDFs, compiled code) are skipped.
- **100 KB per file, 500 KB total:** Very large files need to be chunked manually.
- **Token counts are approximate:** The saved-token metric uses provider-reported token counts, which may not exactly match Claude's tokenizer. Good for directional tracking, not precise accounting.
- **No retry on rate limits:** If the provider returns 429, the tool tells you to wait. No automatic retry or queue.

---

## File structure

```
server.py           → MCP server, one tool, provider routing
openrouter.py       → OpenRouter API client (default)
cloudflare.py       → Cloudflare Workers AI client (alternative)
files.py            → Disk reads, binary detection, size caps
tool_description.py → Tool description Claude reads to decide when to call us
logger.py           → Appends to log.jsonl
stats.py            → CLI stats viewer
log.jsonl           → Append-only call log (gitignored)
.env                → Your API credentials (gitignored)
.env.example        → Template for .env
CLAUDE.md.snippet   → Paste into your project's CLAUDE.md
```

---

## Requirements

- Python 3.10+
- Claude Code (with MCP server support)
- An API key from [OpenRouter](https://openrouter.ai/keys) (free) or a [Cloudflare](https://dash.cloudflare.com) account (free)

---

## License

MIT — see [LICENSE](LICENSE).
