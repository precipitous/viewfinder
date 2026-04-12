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

## Phase 2 -- Persistence & Local LLM (current)

- [ ] SQLite storage layer (videos, transcripts, summaries)
- [ ] Deduplication; skip re-fetching if transcript exists
- [ ] Cost tracking (tokens in/out per summary, cumulative)
- [ ] Pluggable LLM backend interface
- [ ] Local Qwen R1 support via OpenAI-compatible API on Trypticon
- [ ] Benchmark: Claude Sonnet vs Haiku vs Qwen R1 on summary quality/cost
- [ ] Whisper fallback for videos without captions (~15% of YouTube)

## Phase 3 -- Ingest Automation

- [ ] Playlist ingestion (all videos in a playlist)
- [ ] Channel ingestion (latest N videos from a channel)
- [ ] RSS/Atom feed monitoring; auto-ingest new uploads
- [ ] Webhook notifications on new summaries
- [ ] Cron/scheduler integration
- [ ] Rate limiting and retry logic for YouTube

## Phase 4 -- Web UI

- [ ] FastAPI backend (REST + WebSocket for progress)
- [ ] React frontend; paste URL, get summary
- [ ] Search across ingested videos (full-text on transcripts)
- [ ] Embedding generation for semantic search
- [ ] Summary comparison view (side-by-side prompt templates)
- [ ] Export to Notion / Google Docs / Markdown files
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
