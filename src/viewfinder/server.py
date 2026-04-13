"""FastAPI web server for Viewfinder.

Provides REST endpoints for video ingestion, transcript/summary retrieval,
search, and a WebSocket for real-time progress updates.

Run with:
    uvicorn viewfinder.server:app --reload
    # or
    viewfinder --serve
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .storage import Storage

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_store: Storage | None = None


def get_store() -> Storage:
    global _store
    if _store is None:
        _store = Storage()
    return _store


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()
    yield
    if _store is not None:
        _store.close()


app = FastAPI(
    title="Viewfinder",
    description="YouTube video ingestion API -- transcripts, screenshots, and AI summaries",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# WebSocket progress hub
# ---------------------------------------------------------------------------


class ProgressHub:
    """Broadcast progress messages to connected WebSocket clients."""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


hub = ProgressHub()


@app.websocket("/ws/progress")
async def websocket_progress(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    url: str
    lang: str = "en"
    translate_to: str | None = None
    prompt: str = "default"
    model: str = "claude-sonnet-4-20250514"
    backend: str = "claude"
    base_url: str | None = None
    transcript_only: bool = False
    api_key: str | None = None
    whisper: bool = True  # auto-fallback to Whisper when subtitles unavailable
    whisper_backend: str = "local"  # "local" (faster-whisper, free) or "groq" (~$0.01/hr)
    whisper_model: str = "small"
    correct: bool = True  # LLM correction pass on Whisper transcripts


class VideoSummary(BaseModel):
    video_id: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    transcript_count: int
    summary_count: int


class SearchResult(BaseModel):
    video_id: str
    title: str | None
    channel: str | None
    language: str
    snippet: str


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.post("/api/ingest")
async def ingest_video(req: IngestRequest):
    """Submit a video URL for ingestion. Returns transcript and optional summary."""
    from .parsing import extract_video_id
    from .transcript import fetch_transcript

    store = get_store()

    try:
        video_id = extract_video_id(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YouTube URL: {req.url}") from e

    await hub.broadcast({"event": "started", "video_id": video_id})

    # Check cache
    target_lang = req.translate_to or req.lang
    transcript = store.get_transcript(video_id, language=target_lang)

    if transcript is None:
        await hub.broadcast({"event": "fetching_transcript", "video_id": video_id})

        loop = asyncio.get_event_loop()
        try:
            transcript = await loop.run_in_executor(
                None,
                lambda: fetch_transcript(
                    video_id,
                    lang=req.lang,
                    translate_to=req.translate_to,
                    whisper=req.whisper,
                    whisper_backend=req.whisper_backend,
                    whisper_model=req.whisper_model,
                    correct=req.correct,
                    verbose=False,
                ),
            )
        except RuntimeError as e:
            await hub.broadcast({"event": "error", "video_id": video_id, "detail": str(e)[:200]})
            raise HTTPException(status_code=502, detail=str(e)[:500]) from e

        store.save_transcript(transcript)

    await hub.broadcast(
        {
            "event": "transcript_ready",
            "video_id": video_id,
            "word_count": transcript.word_count,
        }
    )

    result = {
        "video_id": video_id,
        "title": transcript.meta.title,
        "channel": transcript.meta.channel,
        "language": transcript.language,
        "translated_from": transcript.translated_from,
        "word_count": transcript.word_count,
        "source": transcript.source.value,
    }

    if not req.transcript_only:
        from .summarize import PROMPTS, summarize

        # Check for custom prompt template
        custom_template = store.get_custom_prompt(req.api_key or "anonymous", req.prompt)
        if custom_template:
            PROMPTS[req.prompt] = custom_template

        await hub.broadcast({"event": "summarizing", "video_id": video_id})

        loop = asyncio.get_event_loop()
        try:
            summary = await loop.run_in_executor(
                None,
                lambda: summarize(
                    transcript,
                    prompt_key=req.prompt,
                    model=req.model,
                    backend=req.backend,
                    base_url=req.base_url,
                    verbose=False,
                ),
            )
        except Exception as e:
            await hub.broadcast({"event": "error", "video_id": video_id, "detail": str(e)[:200]})
            raise HTTPException(status_code=502, detail=f"Summarization failed: {e!s:.500}") from e

        tid = store.save_transcript(transcript)
        store.save_summary(summary, tid)

        result["summary"] = summary.summary
        result["model"] = summary.model
        result["prompt_template"] = summary.prompt_template
        result["input_tokens"] = summary.input_tokens
        result["output_tokens"] = summary.output_tokens

        # Log usage
        store.log_usage(
            api_key=req.api_key or "anonymous",
            endpoint="/api/ingest",
            video_id=video_id,
            input_tokens=summary.input_tokens or 0,
            output_tokens=summary.output_tokens or 0,
        )

    await hub.broadcast({"event": "completed", "video_id": video_id})
    return result


@app.get("/api/videos", response_model=list[VideoSummary])
async def list_videos(limit: int = Query(default=50, le=500)):
    """List all ingested videos."""
    store = get_store()
    return store.list_videos(limit=limit)


@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    """Get details for a specific video including transcripts and summaries."""
    store = get_store()
    meta = store.get_video(video_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Video not found: {video_id}")

    transcript = store.get_transcript(video_id)
    summaries = store.get_summaries(video_id)

    return {
        "video_id": meta.video_id,
        "title": meta.title,
        "channel": meta.channel,
        "duration_seconds": meta.duration_seconds,
        "url": meta.url,
        "transcript": {
            "language": transcript.language if transcript else None,
            "word_count": transcript.word_count if transcript else 0,
            "text": transcript.full_text if transcript else None,
            "translated_from": transcript.translated_from if transcript else None,
        },
        "summaries": summaries,
    }


@app.get("/api/videos/{video_id}/transcript")
async def get_transcript(video_id: str, lang: str = "en"):
    """Get the full transcript for a video."""
    store = get_store()
    transcript = store.get_transcript(video_id, language=lang)
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")

    return {
        "video_id": video_id,
        "language": transcript.language,
        "translated_from": transcript.translated_from,
        "word_count": transcript.word_count,
        "source": transcript.source.value,
        "snippets": [
            {"text": s.text, "start": s.start, "duration": s.duration} for s in transcript.snippets
        ],
    }


@app.get("/api/search", response_model=list[SearchResult])
async def search(q: str = Query(..., min_length=1), limit: int = Query(default=20, le=100)):
    """Full-text search across all transcripts."""
    store = get_store()
    results = store.search_transcripts(q, limit=limit)
    return results


@app.get("/api/cost")
async def cost_report():
    """Get cumulative token usage and cost report."""
    store = get_store()
    return {
        "summary": store.get_cost_summary(),
        "by_model": store.get_cost_by_model(),
    }


# ---------------------------------------------------------------------------
# API key management (admin only)
# ---------------------------------------------------------------------------


class CreateKeyRequest(BaseModel):
    name: str
    is_admin: bool = False
    rate_limit_rpm: int = 30


@app.post("/api/keys")
async def create_api_key(req: CreateKeyRequest):
    """Create a new API key. First key created becomes admin automatically."""

    store = get_store()
    # If no keys exist, first key is always admin
    existing = store.list_api_keys()
    is_admin = req.is_admin or len(existing) == 0
    key = store.create_api_key(req.name, is_admin=is_admin, rate_limit_rpm=req.rate_limit_rpm)
    return {"key": key, "name": req.name, "is_admin": is_admin}


@app.get("/api/keys")
async def list_api_keys():
    """List all API keys (admin only)."""
    store = get_store()
    keys = store.list_api_keys()
    # Mask key values for security -- show first 8 chars only
    for k in keys:
        k["key"] = k["key"][:11] + "..."
    return keys


@app.delete("/api/keys/{key}")
async def delete_api_key(key: str):
    """Delete an API key (admin only)."""
    store = get_store()
    if store.delete_api_key(key):
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="API key not found")


# ---------------------------------------------------------------------------
# Usage metering
# ---------------------------------------------------------------------------


@app.get("/api/usage/{api_key}")
async def get_usage(api_key: str):
    """Get usage stats for an API key."""
    store = get_store()
    record = store.get_api_key(api_key)
    if record is None:
        raise HTTPException(status_code=404, detail="API key not found")
    usage = store.get_usage(api_key)
    return {"api_key": api_key[:11] + "...", "name": record["name"], **usage}


# ---------------------------------------------------------------------------
# Custom prompt templates
# ---------------------------------------------------------------------------


class CustomPromptRequest(BaseModel):
    name: str
    template: str


@app.post("/api/prompts")
async def create_custom_prompt(req: CustomPromptRequest, api_key: str = Query(None)):
    """Create or update a custom prompt template."""
    store = get_store()
    key = api_key or "anonymous"
    store.save_custom_prompt(key, req.name, req.template)
    return {"name": req.name, "saved": True}


@app.get("/api/prompts")
async def list_custom_prompts(api_key: str = Query(None)):
    """List custom prompt templates."""
    from .summarize import PROMPTS

    store = get_store()
    key = api_key or "anonymous"
    custom = store.list_custom_prompts(key)
    builtin = [{"name": k, "builtin": True} for k in PROMPTS]
    return {"builtin": builtin, "custom": custom}


@app.delete("/api/prompts/{name}")
async def delete_custom_prompt(name: str, api_key: str = Query(None)):
    """Delete a custom prompt template."""
    store = get_store()
    key = api_key or "anonymous"
    if store.delete_custom_prompt(key, name):
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Prompt template not found")


@app.get("/api/videos/{video_id}/export.md")
async def export_markdown(video_id: str):
    """Export a video's data as a standalone Markdown file."""
    from .formatters import to_ingest_markdown
    from .models import IngestResult

    store = get_store()
    meta = store.get_video(video_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Video not found: {video_id}")

    transcript = store.get_transcript(video_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="No transcript found")

    from .models import SummaryResult

    summaries = store.get_summaries(video_id)
    summary_obj = None
    if summaries:
        s = summaries[0]
        summary_obj = SummaryResult(
            transcript=transcript,
            summary=s["summary"],
            model=s["model"],
            prompt_template=s["prompt_template"],
            input_tokens=s.get("input_tokens"),
            output_tokens=s.get("output_tokens"),
            generated_at=s.get("generated_at", ""),
        )

    ingest = IngestResult(transcript=transcript, summary=summary_obj)
    md = to_ingest_markdown(ingest)

    return HTMLResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{video_id}.md"'},
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    from . import __version__

    store = get_store()
    return {
        "status": "ok",
        "version": __version__,
        "videos": store.video_count(),
    }


# ---------------------------------------------------------------------------
# Web UI (served from static/index.html)
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent / "static"
_INDEX_HTML = ""  # loaded lazily


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the web UI."""
    global _INDEX_HTML
    if not _INDEX_HTML:
        html_path = _STATIC_DIR / "index.html"
        _INDEX_HTML = html_path.read_text(encoding="utf-8")
    return _INDEX_HTML
