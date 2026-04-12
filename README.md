# Viewfinder

YouTube video ingestion engine. Extracts transcripts (any language), captures screenshots, and generates AI-powered summaries. Makes video content consumable by LLMs.

Named after the Decepticon [Viewfinder](https://tfwiki.net/wiki/Viewfinder_(G1)) -- one of the Reflector trio who merge into a camera.

Built by [Precipitous LLC](https://precipitous.io).

## Quick Start

```bash
# Install
pip install -e .

# Set API key (only needed for summaries)
export ANTHROPIC_API_KEY="sk-ant-..."

# Transcript only (free, no key)
viewfinder https://youtube.com/watch?v=VIDEO_ID --transcript-only

# Translate transcript to Spanish
viewfinder VIDEO_ID --transcript-only --translate-to es

# Screenshots every 30 seconds (requires ffmpeg)
viewfinder VIDEO_ID --screenshots --output-dir ./out

# Full ingest: transcript + screenshots + summary
viewfinder VIDEO_URL --screenshots --output-dir ./out

# Summarize
viewfinder VIDEO_ID

# Detailed analysis
viewfinder VIDEO_ID --prompt detailed --format md --output-dir ./summaries
```

## How It Works

```
URL/ID --> Parser --> Fallback Chain --> Transcript --+--> Claude API --> Summary
                      |                    |          |
                      +-- youtube-transcript-api      +--> ffmpeg --> Screenshots
                      +-- yt-dlp (fallback)           |
                      |                               +--> IngestResult (for LLMs)
                      +-- translate via YouTube API
```

**Transcript extraction** uses a fallback chain. The primary method (`youtube-transcript-api`) is fast and requires no API key. If it fails, `yt-dlp` provides broader compatibility and also supplies video metadata (title, channel, duration).

**Translation** uses YouTube's built-in translation service via `youtube-transcript-api`. Pass `--translate-to es` (or any language code) to get a translated transcript. Use `--list-languages` to see what's available.

**Screenshots** download the video via `yt-dlp` and extract frames at configurable intervals using `ffmpeg`. The video is downloaded to a temp directory and deleted after extraction (use `--keep-video` to retain it).

**Summarization** sends the transcript to Claude with one of four built-in prompt templates. Custom templates are trivial to add.

## Usage

### Transcript Only

```bash
viewfinder VIDEO_URL --transcript-only                    # Plain text
viewfinder VIDEO_URL --transcript-only --timestamps       # With timestamps
viewfinder VIDEO_URL --transcript-only --format json      # Structured JSON
```

### Translation

```bash
viewfinder VIDEO_ID --list-languages                      # See available languages
viewfinder VIDEO_ID --transcript-only --translate-to es   # Spanish
viewfinder VIDEO_ID --transcript-only --translate-to ja   # Japanese
viewfinder VIDEO_ID --translate-to fr --prompt brief      # Summarize French translation
```

### Screenshots

```bash
# Extract screenshots every 30 seconds (default)
viewfinder VIDEO_ID --screenshots --output-dir ./out

# Every 60 seconds, keep the downloaded video
viewfinder VIDEO_ID --screenshots --screenshot-interval 60 --keep-video --output-dir ./out

# Transcript + screenshots as JSON (for LLM consumption)
viewfinder VIDEO_ID --screenshots --transcript-only --format json --output-dir ./out
```

Requires `ffmpeg` installed on the system (`sudo apt install ffmpeg` or `brew install ffmpeg`).

### Summary Prompts

| Template   | Use case                                    | Output length |
|------------|---------------------------------------------|---------------|
| `brief`    | Quick scan; "what is this about?"           | Short         |
| `default`  | TL;DR + key points + notable quotes + tags  | Medium        |
| `detailed` | Section-by-section with timestamps          | Long          |
| `technical`| Extract concepts, tools, code, architecture | Medium-Long   |

```bash
viewfinder VIDEO_ID --prompt brief
viewfinder VIDEO_ID --prompt detailed
viewfinder VIDEO_ID --prompt technical
```

### Output Formats

```bash
viewfinder VIDEO_ID --format md       # Markdown (default)
viewfinder VIDEO_ID --format json     # Structured JSON
viewfinder VIDEO_ID --format text     # Plain text
```

### Batch Processing

```bash
# urls.txt: one URL/ID per line, # comments allowed
viewfinder --batch urls.txt --output-dir ./summaries
```

### Model Selection

```bash
viewfinder VIDEO_ID --model claude-haiku-4-5-20251001    # Cheaper, faster
viewfinder VIDEO_ID --model claude-sonnet-4-20250514     # Balanced (default)
```

## Programmatic Usage

```python
from viewfinder.parsing import extract_video_id
from viewfinder.transcript import fetch_transcript
from viewfinder.screenshots import capture_screenshots
from viewfinder.summarize import summarize
from viewfinder.models import IngestResult

video_id = extract_video_id("https://youtube.com/watch?v=VIDEO_ID")

# Transcript (optionally translated)
transcript = fetch_transcript(video_id, translate_to="es")
print(f"{transcript.word_count} words, translated from {transcript.translated_from}")

# Screenshots
shots = capture_screenshots(video_id, output_dir="./out", interval=30)
print(f"{len(shots.screenshots)} screenshots captured")

# Combined ingest result for LLM consumption
ingest = IngestResult(transcript=transcript, screenshots=shots)

# Summarize
summary = summarize(transcript, prompt_key="detailed")
print(summary.summary)
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

See [CLAUDE.md](CLAUDE.md) for development conventions and [ROADMAP.md](ROADMAP.md) for the full plan.

## License

MIT
