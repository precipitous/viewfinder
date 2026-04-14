# Viewfinder Roadmap

## Phase 1 -- CLI Foundation (COMPLETE)

- [x] YouTube URL/ID parsing (all formats)
- [x] Transcript extraction via youtube-transcript-api
- [x] Fallback extraction via yt-dlp
- [x] Metadata enrichment
- [x] Claude API summarization
- [x] 4 prompt templates (brief, default, detailed, technical)
- [x] JSON / Markdown / text output
- [x] Batch processing from file
- [x] Output directory support
- [x] Unit tests for parsing, models, formatters
- [x] Integration tests (network-dependent, tagged)
- [x] CI via GitHub Actions

## Phase 1.5 -- LLM Video Ingestion (COMPLETE)

- [x] Transcript translation to any language (via YouTube API)
- [x] List available transcript languages (--list-languages)
- [x] Screenshot extraction via ffmpeg at configurable intervals
- [x] Video download via yt-dlp (temp or persistent)
- [x] IngestResult model combining transcript + screenshots
- [x] Combined ingest formatters (JSON, Markdown)
- [x] Unit tests for screenshots, translation, ingest models

## Phase 2 -- Persistence & Local LLM (COMPLETE)

- [x] SQLite storage layer (videos, transcripts, summaries, screenshots)
- [x] Deduplication; skip re-fetching if transcript exists
- [x] Cost tracking (tokens in/out per summary, cumulative --cost-report)
- [x] Pluggable LLM backend interface (claude + openai-compatible)
- [x] Local Qwen R1 support via OpenAI-compatible API on Nemesis (Ollama port 11434)
- [x] Whisper fallback: dual backend (local faster-whisper on GPU + Groq cloud API)
- [x] --whisper-only flag to skip subtitle fetch (avoids YouTube rate limits)
- [x] Phonetic transcript correction using video title context (instant, no LLM)

## Phase 3 -- Ingest Automation (COMPLETE)

- [x] Playlist ingestion (--playlist URL)
- [x] Channel ingestion (--channel URL --channel-limit N)
- [x] RSS/Atom feed monitoring (--feed CHANNEL_ID)
- [x] Webhook notifications (--webhook-url URL)
- [x] Rate limiting and retry logic (--rate-limit N, exponential backoff)
- [x] Global YouTube rate limiter (2s between all API calls, thread-safe)
- [x] Input deduplication across all sources

## Phase 4 -- Web UI (COMPLETE)

- [x] FastAPI backend (REST + WebSocket for progress)
- [x] Built-in SPA frontend (paste URL, progress, search, video browser)
- [x] Full-text search across transcripts (FTS5)
- [x] Export to Markdown files (CLI --export and REST endpoint)
- [x] CLI --search and --serve flags
- [x] Whisper backend selector in web UI (Off / Local GPU / Groq Cloud)

## Phase 5 -- Public Product (COMPLETE)

- [x] API key auth with per-key rate limiting (requests/minute)
- [x] Usage metering per API key (requests, tokens, unique videos)
- [x] Custom prompt templates per API key (CRUD via REST)
- [x] Chrome extension: Manifest V3, "Summarize" button on YouTube pages

## Phase 6 -- Production Library (COMPLETE)

- [x] Per-video output folders (transcript.md + transcript.json + screenshots/)
- [x] 10-second screenshot intervals for code tutorials
- [x] Batch processing: 44 videos, 548K words, 15K screenshots in ~65 minutes
- [x] Library at /home/megatron/viewfinder-library/ organized by topic

## What's Next

### Viewfinder improvements
- [ ] GPU-accelerated ffmpeg for dense frame extraction
- [ ] Groq API key setup for fast cloud Whisper
- [ ] NordVPN proxy integration for YouTube rate limit bypass
- [ ] Embedding generation for semantic search
- [ ] Scene change detection (smart screenshot intervals)
- [ ] Automatic topic categorization of ingested videos

### Shrapnel integration
- [ ] Build Shrapnel (self-replicating project spawner)
- [ ] Viewfinder as ingestion engine for Shrapnel
- [ ] API endpoint for programmatic batch ingest from Shrapnel
- [ ] See SHRAPNEL_PLAN.md for full plan

### Content pipeline
- [ ] Mortgage/lending video library for LendSight
- [ ] Auto-ingest from subscribed channels via RSS
- [ ] Summary comparison: Claude vs Haiku vs local Qwen
