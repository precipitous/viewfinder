# CLAUDE.md -- Viewfinder

## Project Overview

Viewfinder is a YouTube video ingestion engine built by Precipitous LLC. It extracts transcripts (with Whisper fallback for when subtitles are unavailable or rate-limited), captures screenshots via ffmpeg at configurable intervals, and generates AI-powered summaries using pluggable LLM backends. Designed to make video content consumable by LLMs. Named after the Decepticon Viewfinder (one of the Reflector trio who merge into a camera).

**Viewfinder feeds Shrapnel** -- a sister project that ingests video knowledge and forks itself into fully-scaffolded new projects. See SHRAPNEL_PLAN.md for details.

## Architecture

```
src/viewfinder/
  __init__.py       -- Package root, version (1.0.0)
  models.py         -- Data models (TranscriptSnippet, VideoMeta, TranscriptResult,
                       Screenshot, ScreenshotResult, IngestResult, SummaryResult)
  parsing.py        -- YouTube URL/ID extraction
  transcript.py     -- Fallback chain: subtitles (ytt -> yt-dlp) -> Whisper (local/Groq)
                       Global YouTube rate limiter (2s between requests)
                       Phonetic transcript correction using title context
  screenshots.py    -- Video download (yt-dlp) + frame extraction (ffmpeg)
  summarize.py      -- Pluggable LLM backends (Claude API, OpenAI-compatible) + prompts
  formatters.py     -- Output formatting (JSON, Markdown, plain text)
  storage.py        -- SQLite persistence (videos, transcripts, summaries, API keys,
                       usage, custom prompts, FTS5 full-text search)
  ingest.py         -- Bulk ingestion: playlists, channels, RSS feeds, webhooks, rate limiting
  server.py         -- FastAPI web server (REST API + WebSocket + built-in SPA)
  auth.py           -- API key authentication and rate limiting middleware
  cli.py            -- CLI entry point (installed as `viewfinder` command)
  static/index.html -- Web UI (dark theme, sidebar nav, search, video browser)

chrome-extension/   -- Manifest V3 Chrome extension for one-click YouTube summarization
```

## Key Design Decisions

- **Single-responsibility modules**: Each file does one thing. Models are pure dataclasses with no IO.
- **Fallback chain pattern**: Subtitles first (ytt -> yt-dlp), then Whisper. Use --whisper-only to skip subtitle attempts entirely (avoids YouTube rate limits).
- **Dual Whisper backends**: Local (faster-whisper on GPU, free, ~61x realtime on 3090) or Groq cloud (~$0.01/hr, near-instant). Use --fast for Groq.
- **Phonetic transcript correction**: After Whisper transcription, automatically fixes misheard proper nouns using video title context. No LLM needed -- pure phonetic matching. Instant (<0.02s).
- **Global YouTube rate limiter**: 2-second minimum between all YouTube API calls, thread-safe. Prevents the burst-request pattern that triggers IP blocks.
- **Translation via YouTube API**: Uses youtube-transcript-api's built-in .translate() method.
- **Screenshots at any interval**: Default 10s for code tutorials (catches every screen change). Stored alongside transcripts in per-video folders.
- **Pluggable LLM backends**: Claude API (default) or any OpenAI-compatible endpoint (Ollama/vLLM/Groq) via --backend openai --base-url.
- **SQLite with FTS5**: Full-text search across all transcripts. API keys, usage metering, custom prompts all in the same DB.

## Video Library

Processed videos are stored in:
- **Database**: ~/.viewfinder/viewfinder.db (transcripts, metadata, summaries)
- **Files**: /home/megatron/viewfinder-library/{topic}/{video_id}/
  - transcript.md (timestamped, human-readable)
  - transcript.json (structured data)
  - screenshots/{video_id}/frame_NNNN.jpg (every 10s)

Current library: 44 videos, 548K+ words, 15K+ screenshots, 565MB

## Development Commands

```bash
# Install in editable mode with dev deps
pip install -e ".[dev,server]"

# Run CLI
viewfinder VIDEO_URL --transcript-only              # subtitles first, whisper fallback
viewfinder VIDEO_URL --whisper-only                  # skip subtitles entirely
viewfinder VIDEO_URL --whisper-only --fast            # use Groq cloud instead of local GPU
viewfinder VIDEO_URL --screenshots --output-dir ./out # 10s interval screenshots
viewfinder VIDEO_URL --prompt detailed --format json  # AI summary

# Bulk ingestion
viewfinder --playlist "PLAYLIST_URL" --whisper-only --output-dir ./out
viewfinder --channel "CHANNEL_URL" --channel-limit 20 --output-dir ./out

# Web server
viewfinder --serve --port 8080

# Database queries
viewfinder --list-videos
viewfinder --search "machine learning"
viewfinder --cost-report
viewfinder --export VIDEO_ID

# Run tests
pytest
pytest -m "not network"    # skip YouTube-dependent tests

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Conventions

- Python 3.10+ required. Use modern type hints (list[str] not List[str]).
- No em dashes in any output or documentation; use semicolons or standard hyphens.
- Use ruff for linting and formatting. Config is in pyproject.toml.
- All IO/network calls happen in transcript.py, screenshots.py, and summarize.py. Models and formatters are pure.
- Progress/debug output goes to stderr. Actual output goes to stdout.
- Verbose logging is opt-in via `verbose=True` parameter (default on in CLI).
- Dark theme UI: #0d1117 bg, #161b22 surface, #30363d border, #c9d1d9 text, #58a6ff accent.

## Infrastructure Context

This project is part of the Precipitous LLC / Decepticons ecosystem:
- **Nemesis** (formerly Shockwave): Development workstation, single RTX 3090, runs Ollama (Qwen2 32B) on port 11434
- **Soundwave**: Ubuntu server at 192.168.2.111; hosts Mattermost and nginx
- **Viewfinder server**: http://192.168.2.229:8080 (this project's web UI and API)

## Environment Variables

| Variable           | Required | Description                            |
|--------------------|----------|----------------------------------------|
| ANTHROPIC_API_KEY  | For summaries only | Claude API key              |
| GROQ_API_KEY       | For --fast whisper | Groq API key (free tier available) |
| NORDVPN_USER       | Optional | NordVPN service username (for proxy) |
| NORDVPN_PASS       | Optional | NordVPN service password |

## System Dependencies

| Tool            | Required for        | Install                         |
|-----------------|---------------------|---------------------------------|
| ffmpeg          | Screenshots         | `sudo apt install ffmpeg`       |
| faster-whisper  | Local transcription | `pip install faster-whisper`    |
| CUDA            | GPU Whisper         | Needs NVIDIA driver + CUDA 12.x |

## Testing

125 unit tests + 13 integration tests. Network tests auto-skip on YouTube rate limits via conftest.py hook.

## Shrapnel Integration

Viewfinder is the ingestion engine for Shrapnel (the project spawner). When Shrapnel needs to learn from a YouTube video, it calls:

```bash
viewfinder VIDEO_URL --whisper-only --transcript-only --format json --output-dir ~/shrapnel/library/
```

Or via API:
```bash
curl -X POST http://192.168.2.229:8080/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"url": "VIDEO_URL", "whisper_only": true, "transcript_only": true}'
```

See SHRAPNEL_PLAN.md for the full Shrapnel project plan.

## Roadmap

See ROADMAP.md for the full plan.
