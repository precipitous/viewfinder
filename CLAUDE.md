# CLAUDE.md — Viewfinder

## Project Overview

Viewfinder is a YouTube video ingestion engine built by Precipitous LLC. It extracts transcripts (translatable to any language), captures screenshots via ffmpeg, and generates AI-powered summaries using Claude. Designed to make video content consumable by LLMs. Named after the Decepticon Viewfinder (one of the Reflector trio who merge into a camera).

## Architecture

```
src/viewfinder/
  __init__.py       -- Package root, version
  models.py         -- Data models (TranscriptSnippet, VideoMeta, TranscriptResult,
                       Screenshot, ScreenshotResult, IngestResult, SummaryResult)
  parsing.py        -- YouTube URL/ID extraction
  transcript.py     -- Fallback chain: youtube-transcript-api -> yt-dlp -> whisper
  screenshots.py    -- Video download (yt-dlp) + frame extraction (ffmpeg)
  summarize.py      -- Pluggable LLM backends (Claude API, OpenAI-compatible) + prompts
  formatters.py     -- Output formatting (JSON, Markdown, plain text)
  storage.py        -- SQLite persistence (videos, transcripts, summaries, API keys, usage, FTS)
  ingest.py         -- Bulk ingestion: playlists, channels, RSS feeds, webhooks, rate limiting
  server.py         -- FastAPI web server (REST API + WebSocket + built-in SPA)
  auth.py           -- API key authentication and rate limiting middleware
  cli.py            -- CLI entry point (installed as `viewfinder` command)

chrome-extension/   -- Manifest V3 Chrome extension for one-click YouTube summarization
```

## Key Design Decisions

- **Single-responsibility modules**: Each file does one thing. Models are pure dataclasses with no IO.
- **Fallback chain pattern**: `transcript.py` tries youtube-transcript-api first (fast, no key), then yt-dlp (broader compat + metadata). Both methods are independently callable.
- **Translation via YouTube API**: Transcript translation uses youtube-transcript-api's built-in `.translate()` method, which leverages YouTube's own translation service. No external translation API needed.
- **Screenshots via ffmpeg**: `screenshots.py` downloads the video via yt-dlp, then uses ffmpeg to extract frames at configurable intervals. Video is downloaded to a temp dir by default (deleted after extraction).
- **Metadata enrichment**: If ytt gives us a transcript but no metadata, we call yt-dlp separately just for metadata. This is optional and skippable (--no-enrich).
- **Prompt templates are data**: Stored as a plain dict in `summarize.py`. Easy to add new ones; no class hierarchy needed.
- **No database yet**: MVP is stateless CLI. SQLite persistence is on the roadmap.

## Development Commands

```bash
# Install in editable mode with dev deps
pip install -e ".[dev]"

# Run CLI
viewfinder VIDEO_URL --transcript-only
viewfinder VIDEO_URL --transcript-only --translate-to es
viewfinder VIDEO_URL --screenshots --output-dir ./out
viewfinder VIDEO_URL --prompt detailed --format json

# Run tests
pytest

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Conventions

- Python 3.10+ required. Use modern type hints (list[str] not List[str]).
- No em dashes in any output or documentation; use semicolons or standard hyphens.
- Use ruff for linting and formatting. Config is in pyproject.toml.
- All IO/network calls happen in transcript.py and summarize.py. Models and formatters are pure.
- Progress/debug output goes to stderr. Actual output goes to stdout.
- Verbose logging is opt-in via `verbose=True` parameter (default on in CLI).

## Infrastructure Context

This project is part of the Precipitous LLC ecosystem:
- **Scourge**: Development workstation
- **Trypticon** (or current name): Dual RTX 3090 server; can run local LLM inference (Qwen R1)
- **Soundwave**: Ubuntu server at 192.168.2.111; hosts Mattermost and nginx

Future: the summarization backend should support swappable LLM providers so we can benchmark Claude API vs local Qwen R1 on Trypticon for cost optimization.

## Environment Variables

| Variable           | Required | Description                            |
|--------------------|----------|----------------------------------------|
| ANTHROPIC_API_KEY  | For summaries only | Claude API key              |

## System Dependencies

| Tool    | Required for        | Install                         |
|---------|---------------------|---------------------------------|
| ffmpeg  | Screenshots only    | `sudo apt install ffmpeg` (Linux) / `brew install ffmpeg` (macOS) |

## Testing

Tests live in `tests/`. The transcript extraction tests require network access and may fail from cloud IPs (YouTube blocks them). Use `@pytest.mark.network` to tag those.

Unit tests for parsing, models, and formatters should always pass without network.

## Adding a New Prompt Template

1. Add an entry to `PROMPTS` dict in `src/viewfinder/summarize.py`
2. Use `{title}`, `{channel}`, `{duration}`, `{transcript}` placeholders
3. The CLI automatically picks up new keys via `choices=list(PROMPTS.keys())`
4. No other changes needed

## Adding a New Extraction Strategy

1. Add a `fetch_via_*` function in `src/viewfinder/transcript.py`
2. Add it to the fallback chain in `fetch_transcript()`
3. Add a corresponding `TranscriptSource` enum value in `models.py`

## Roadmap

See ROADMAP.md for the full plan.
