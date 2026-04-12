# Viewfinder Roadmap

## Phase 1 -- CLI Foundation

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

## Phase 1.5 -- LLM Video Ingestion

- [x] Transcript translation to any language (via YouTube API)
- [x] List available transcript languages (--list-languages)
- [x] Screenshot extraction via ffmpeg at configurable intervals
- [x] Video download via yt-dlp (temp or persistent)
- [x] IngestResult model combining transcript + screenshots
- [x] Combined ingest formatters (JSON, Markdown)
- [x] Unit tests for screenshots, translation, ingest models

## Phase 2 -- Persistence & Local LLM

- [x] SQLite storage layer (videos, transcripts, summaries, screenshots)
- [x] Deduplication; skip re-fetching if transcript exists
- [x] Cost tracking (tokens in/out per summary, cumulative --cost-report)
- [x] Pluggable LLM backend interface (claude + openai-compatible)
- [x] Local Qwen R1 support via OpenAI-compatible API on Trypticon
- [x] Whisper fallback for videos without captions (~15% of YouTube)
- [ ] Benchmark: Claude Sonnet vs Haiku vs Qwen R1 on summary quality/cost

## Phase 3 -- Ingest Automation

- [x] Playlist ingestion (--playlist URL)
- [x] Channel ingestion (--channel URL --channel-limit N)
- [x] RSS/Atom feed monitoring (--feed CHANNEL_ID)
- [x] Webhook notifications (--webhook-url URL)
- [x] Rate limiting and retry logic (--rate-limit N, exponential backoff)
- [x] Input deduplication across all sources
- [ ] Cron/scheduler integration

## Phase 4 -- Web UI

- [x] FastAPI backend (REST + WebSocket for progress)
- [x] Built-in SPA frontend (paste URL, progress, search, video browser)
- [x] Full-text search across transcripts (FTS5)
- [x] Export to Markdown files (CLI --export and REST endpoint)
- [x] CLI --search and --serve flags
- [ ] Embedding generation for semantic search
- [ ] Summary comparison view (side-by-side prompt templates)
- [ ] User accounts (if public-facing)

## Phase 5 -- Public Product

- [ ] Landing page under Precipitous / LendSight branding
- [ ] API rate limiting and auth (API keys)
- [ ] Usage metering and billing
- [ ] Chrome extension: one-click summarize from YouTube
- [ ] Slack/Discord bot integration
- [ ] Custom prompt templates per user

## Open Questions

- Should we support non-YouTube platforms (Vimeo, Twitch VODs)?
- Is there a market for mortgage-specific video analysis (rate commentary, market updates)?
- Local-first vs cloud-first for the web UI deployment?
