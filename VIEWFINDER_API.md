# Viewfinder API Integration Guide

You are integrating with Viewfinder, a YouTube video ingestion API. It extracts transcripts, translates them, captures screenshots, and generates AI summaries. Use this document as your complete reference for building API connections.

## Server

- **Base URL**: `http://192.168.2.229:8080`
- **Protocol**: HTTP REST (JSON)
- **Real-time updates**: WebSocket at `ws://192.168.2.229:8080/ws/progress`
- **Interactive docs**: http://192.168.2.229:8080/docs (Swagger UI)
- **Auth**: Optional API key via `X-API-Key` header. If no keys have been created, auth is disabled (open access).

## Quick Start

```bash
# Health check
curl http://192.168.2.229:8080/api/health

# Get transcript only (no API key needed, free)
curl -X POST http://192.168.2.229:8080/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://youtube.com/watch?v=VIDEO_ID", "transcript_only": true}'

# Get transcript + AI summary
curl -X POST http://192.168.2.229:8080/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"url": "VIDEO_ID", "prompt": "detailed"}'

# Search across all ingested transcripts
curl "http://192.168.2.229:8080/api/search?q=machine+learning"

# List all ingested videos
curl http://192.168.2.229:8080/api/videos

# Get full details for a specific video
curl http://192.168.2.229:8080/api/videos/VIDEO_ID
```

---

## Endpoints

### POST /api/ingest

The primary endpoint. Submit a YouTube URL; get back transcript and optional summary.

**Request body:**

```json
{
  "url": "https://youtube.com/watch?v=VIDEO_ID",  // REQUIRED - YouTube URL or bare video ID
  "transcript_only": false,    // true = skip summarization (faster, free)
  "prompt": "default",         // "default" | "brief" | "detailed" | "technical"
  "model": "claude-sonnet-4-20250514",  // or "claude-haiku-4-5-20251001" (cheaper)
  "lang": "en",               // preferred transcript language
  "translate_to": null,        // "es", "fr", "ja", etc. -- translates via YouTube
  "backend": "claude",         // "claude" (Anthropic) or "openai" (OpenAI-compatible)
  "base_url": null             // for openai backend, e.g. "http://trypticon:8000"
}
```

Only `url` is required. All other fields have defaults.

**Response (transcript_only=true):**

```json
{
  "video_id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "channel": "Rick Astley",
  "language": "en",
  "translated_from": null,
  "word_count": 2847,
  "source": "youtube-transcript-api"
}
```

**Response (with summary):**

```json
{
  "video_id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "channel": "Rick Astley",
  "language": "en",
  "translated_from": null,
  "word_count": 2847,
  "source": "youtube-transcript-api",
  "summary": "## TL;DR\n\nThe video is a music video for...",
  "model": "claude-sonnet-4-20250514",
  "prompt_template": "default",
  "input_tokens": 3200,
  "output_tokens": 450
}
```

**Error responses:**
- `400` - Invalid YouTube URL
- `500` - Transcript extraction failed (YouTube rate limit, video unavailable, etc.)

**Notes:**
- Results are cached in SQLite. Repeated requests for the same video return instantly from cache.
- Summarization requires `ANTHROPIC_API_KEY` set on the server (or use the `openai` backend for local LLMs).

---

### GET /api/videos

List all ingested videos with transcript/summary counts.

**Query params:**
- `limit` (int, default 50, max 500)

**Response:**

```json
[
  {
    "video_id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "channel": "Rick Astley",
    "duration_seconds": 212,
    "transcript_count": 1,
    "summary_count": 2
  }
]
```

---

### GET /api/videos/{video_id}

Full details for a single video: metadata, transcript text, all summaries.

**Response:**

```json
{
  "video_id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "channel": "Rick Astley",
  "duration_seconds": 212,
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "transcript": {
    "language": "en",
    "word_count": 2847,
    "text": "We're no strangers to love, you know the rules...",
    "translated_from": null
  },
  "summaries": [
    {
      "id": 1,
      "summary": "## TL;DR\n\n...",
      "model": "claude-sonnet-4-20250514",
      "prompt_template": "default",
      "input_tokens": 3200,
      "output_tokens": 450,
      "generated_at": "2026-04-12T..."
    }
  ]
}
```

Returns `404` if video not found.

---

### GET /api/videos/{video_id}/transcript

Timestamped transcript snippets for a video.

**Query params:**
- `lang` (string, default "en")

**Response:**

```json
{
  "video_id": "dQw4w9WgXcQ",
  "language": "en",
  "translated_from": null,
  "word_count": 2847,
  "source": "youtube-transcript-api",
  "snippets": [
    {"text": "We're no strangers to love", "start": 0.0, "duration": 3.2},
    {"text": "You know the rules and so do I", "start": 3.2, "duration": 2.8}
  ]
}
```

Returns `404` if no transcript found.

---

### GET /api/search?q={query}

Full-text search across all ingested transcripts (powered by SQLite FTS5).

**Query params:**
- `q` (string, required) - search query
- `limit` (int, default 20, max 100)

**Response:**

```json
[
  {
    "video_id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "channel": "Rick Astley",
    "language": "en",
    "snippet": "...you know the <b>rules</b> and so do I..."
  }
]
```

The `snippet` field contains HTML `<b>` tags around matched terms.

---

### GET /api/videos/{video_id}/export.md

Download a video's data as a standalone Markdown file. Returns `text/markdown` with `Content-Disposition: attachment`.

---

### GET /api/health

**Response:**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "videos": 42
}
```

---

### GET /api/cost

Cumulative token usage across all summaries.

**Response:**

```json
{
  "summary": {
    "total_summaries": 15,
    "total_input_tokens": 48000,
    "total_output_tokens": 12000,
    "total_tokens": 60000
  },
  "by_model": [
    {"model": "claude-sonnet-4-20250514", "count": 12, "input_tokens": 40000, "output_tokens": 10000},
    {"model": "claude-haiku-4-5-20251001", "count": 3, "input_tokens": 8000, "output_tokens": 2000}
  ]
}
```

---

### POST /api/keys

Create an API key. The first key created is always admin.

**Request body:**

```json
{
  "name": "my-app",
  "is_admin": false,
  "rate_limit_rpm": 30
}
```

**Response:**

```json
{
  "key": "vf-a1b2c3d4e5f6...",
  "name": "my-app",
  "is_admin": false
}
```

---

### GET /api/keys

List all API keys (keys are masked in response).

---

### DELETE /api/keys/{key}

Delete an API key.

---

### GET /api/usage/{api_key}

Usage stats for a specific API key.

**Response:**

```json
{
  "api_key": "vf-a1b2c3d...",
  "name": "my-app",
  "total_requests": 47,
  "total_input_tokens": 15000,
  "total_output_tokens": 4200,
  "unique_videos": 23
}
```

---

### POST /api/prompts

Create or update a custom prompt template.

**Request body:**

```json
{
  "name": "my-custom-prompt",
  "template": "Analyze this video transcript for {title} by {channel}.\n\nFocus on: ...\n\nTranscript:\n{transcript}"
}
```

Available placeholders: `{title}`, `{channel}`, `{duration}`, `{transcript}`

---

### GET /api/prompts

List built-in and custom prompt templates.

---

### DELETE /api/prompts/{name}

Delete a custom prompt template.

---

## WebSocket: Real-time Progress

Connect to `ws://192.168.2.229:8080/ws/progress` to receive JSON messages during video processing:

```json
{"event": "started", "video_id": "dQw4w9WgXcQ"}
{"event": "fetching_transcript", "video_id": "dQw4w9WgXcQ"}
{"event": "transcript_ready", "video_id": "dQw4w9WgXcQ", "word_count": 2847}
{"event": "summarizing", "video_id": "dQw4w9WgXcQ"}
{"event": "completed", "video_id": "dQw4w9WgXcQ"}
```

Example JavaScript:

```javascript
const ws = new WebSocket('ws://192.168.2.229:8080/ws/progress');
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  console.log(`${msg.event}: ${msg.video_id}`);
};
```

---

## Prompt Templates

| Name | Description | Output |
|------|-------------|--------|
| `default` | TL;DR + key points + notable quotes + tags | Medium |
| `brief` | 3-5 sentence summary | Short |
| `detailed` | Section-by-section with timestamps, fact-checks, audience assessment | Long |
| `technical` | Technical concepts, tools, architecture, code snippets | Medium-Long |

---

## Python Client Example

```python
import requests

BASE = "http://192.168.2.229:8080"

# Ingest a video
resp = requests.post(f"{BASE}/api/ingest", json={
    "url": "https://youtube.com/watch?v=VIDEO_ID",
    "prompt": "detailed",
})
data = resp.json()
print(data["summary"])

# Search
results = requests.get(f"{BASE}/api/search", params={"q": "machine learning"}).json()
for r in results:
    print(f"{r['title']}: {r['snippet']}")

# Get full transcript with timestamps
transcript = requests.get(f"{BASE}/api/videos/{data['video_id']}/transcript").json()
for s in transcript["snippets"]:
    print(f"[{s['start']:.1f}s] {s['text']}")
```

---

## CLI (alternative to API)

Viewfinder also has a full CLI. The CLI and API share the same SQLite database, so videos ingested via CLI appear in the API and vice versa.

```bash
# Transcript only
viewfinder VIDEO_URL --transcript-only

# Summary
viewfinder VIDEO_URL --prompt detailed

# Translate to Spanish
viewfinder VIDEO_URL --transcript-only --translate-to es

# Ingest entire playlist
viewfinder --playlist "https://youtube.com/playlist?list=PLxxxxx"

# Search cached transcripts
viewfinder --search "machine learning"

# Start the web server
viewfinder --serve --port 8080
```

---

## Architecture Notes

- All results are cached in SQLite (`~/.viewfinder/viewfinder.db`). Repeated requests for the same video are instant.
- Transcript extraction uses a fallback chain: youtube-transcript-api (fast) -> yt-dlp (broader) -> Whisper (local audio transcription, if enabled).
- Translation uses YouTube's built-in translation service via youtube-transcript-api.
- The server runs on FastAPI with uvicorn. CORS is enabled for all origins.
- The OpenAPI spec is available at `/openapi.json`.
