"""Transcript extraction with fallback chain.

Extraction strategies (in order):
    1. youtube-transcript-api  — fast, no API key, ~85% success rate
    2. yt-dlp                  — broader compatibility, also provides video metadata

Translation:
    youtube-transcript-api supports translating transcripts to any language
    YouTube supports. Pass translate_to="es" (etc.) to get a translated version.
"""

import json
import sys
import threading
import time

from .models import TranscriptResult, TranscriptSnippet, TranscriptSource, VideoMeta

# ---------------------------------------------------------------------------
# Global YouTube rate limiter
# ---------------------------------------------------------------------------

_yt_lock = threading.Lock()
_yt_last_request: float = 0.0
_YT_MIN_INTERVAL = 2.0  # seconds between YouTube requests


def _youtube_throttle():
    """Enforce a minimum interval between YouTube API calls."""
    global _yt_last_request
    with _yt_lock:
        now = time.monotonic()
        elapsed = now - _yt_last_request
        if elapsed < _YT_MIN_INTERVAL:
            time.sleep(_YT_MIN_INTERVAL - elapsed)
        _yt_last_request = time.monotonic()


# ---------------------------------------------------------------------------
# Strategy 1: youtube-transcript-api
# ---------------------------------------------------------------------------


def fetch_via_ytt(
    video_id: str,
    lang: str = "en",
    translate_to: str | None = None,
) -> TranscriptResult:
    """Primary method: youtube-transcript-api. Fast, no API key.

    Args:
        video_id: YouTube video ID.
        lang: Preferred transcript language.
        translate_to: If set, translate the transcript to this language code.
    """
    _youtube_throttle()
    from youtube_transcript_api import YouTubeTranscriptApi

    ytt = YouTubeTranscriptApi()

    if translate_to:
        # Use the list -> find -> translate -> fetch flow
        transcript_list = ytt.list(video_id)
        transcript = transcript_list.find_transcript([lang, "en"])
        original_lang = transcript.language_code
        translated = transcript.translate(translate_to)
        fetched = translated.fetch()

        snippets = [
            TranscriptSnippet(text=s.text, start=s.start, duration=s.duration)
            for s in fetched.snippets
        ]

        meta = VideoMeta(video_id=video_id)

        return TranscriptResult(
            meta=meta,
            snippets=snippets,
            source=TranscriptSource.YTT_API,
            language=translate_to,
            translated_from=original_lang,
            is_generated=fetched.is_generated,
        )

    fetched = ytt.fetch(video_id, languages=[lang, "en"])

    snippets = [
        TranscriptSnippet(text=s.text, start=s.start, duration=s.duration) for s in fetched.snippets
    ]

    meta = VideoMeta(video_id=video_id)

    return TranscriptResult(
        meta=meta,
        snippets=snippets,
        source=TranscriptSource.YTT_API,
        language=fetched.language_code,
        is_generated=fetched.is_generated,
    )


# ---------------------------------------------------------------------------
# Strategy 2: yt-dlp
# ---------------------------------------------------------------------------


def fetch_via_ytdlp(
    video_id: str,
    lang: str = "en",
    translate_to: str | None = None,
) -> TranscriptResult:
    """Fallback method: yt-dlp subtitle download + metadata.

    Downloads subtitles to a temp directory (letting yt-dlp handle the HTTP
    request with its own session/cookies), then parses the json3 file.
    """
    _youtube_throttle()
    import tempfile

    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"

    sub_langs = [lang, "en"]
    if translate_to and translate_to not in sub_langs:
        sub_langs.insert(0, translate_to)

    with tempfile.TemporaryDirectory() as tmp_dir:
        outtmpl = f"{tmp_dir}/{video_id}.%(ext)s"
        ydl_opts = {
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": sub_langs,
            "subtitlesformat": "json3",
            "skip_download": True,
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "cookiesfrombrowser": ("chrome",),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        meta = VideoMeta(
            video_id=video_id,
            title=info.get("title"),
            channel=info.get("channel") or info.get("uploader"),
            duration_seconds=info.get("duration"),
            upload_date=info.get("upload_date"),
            description=info.get("description"),
        )

        # Find the downloaded subtitle file
        import glob

        sub_files = glob.glob(f"{tmp_dir}/*.json3")
        is_generated = False
        chosen_lang = lang

        if not sub_files:
            raise RuntimeError(f"No subtitles downloaded via yt-dlp for {video_id}")

        # Pick the best file: prefer manual over auto, prefer requested lang
        sub_file = sub_files[0]
        for f in sub_files:
            fname = f.lower()
            if translate_to and translate_to in fname:
                sub_file = f
                chosen_lang = translate_to
                break
            if f".{lang}." in fname:
                sub_file = f
                chosen_lang = lang
                break

        # Detect if auto-generated
        requested_subs = info.get("requested_subtitles", {})
        for sub_lang, sub_info in requested_subs.items():
            if sub_info and sub_info.get("ext") == "json3":
                chosen_lang = sub_lang
                # If it came from automatic_captions, it's generated
                auto = info.get("automatic_captions", {})
                is_generated = sub_lang in auto and sub_lang not in info.get("subtitles", {})
                break

        with open(sub_file) as f:
            sub_json = json.load(f)

    events = sub_json.get("events", [])
    snippets = []
    for event in events:
        segs = event.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if text and text != "\n":
            snippets.append(
                TranscriptSnippet(
                    text=text,
                    start=event.get("tStartMs", 0) / 1000.0,
                    duration=event.get("dDurationMs", 0) / 1000.0,
                )
            )

    return TranscriptResult(
        meta=meta,
        snippets=snippets,
        source=TranscriptSource.YT_DLP,
        language=chosen_lang,
        is_generated=is_generated,
    )


# ---------------------------------------------------------------------------
# Strategy 3: Whisper (for videos without captions)
# ---------------------------------------------------------------------------


def fetch_via_whisper(
    video_id: str,
    lang: str = "en",
    whisper_model: str = "base",
) -> TranscriptResult:
    """Fallback method: download audio via yt-dlp, transcribe with Whisper.

    Requires the `whisper` CLI to be installed (pip install openai-whisper).
    This is the last resort for videos with no captions at all.

    Args:
        video_id: YouTube video ID.
        lang: Language hint for Whisper.
        whisper_model: Whisper model size (tiny, base, small, medium, large).
    """
    import json as _json
    import shutil
    import subprocess
    import tempfile

    import yt_dlp

    whisper_bin = shutil.which("whisper")
    if not whisper_bin:
        raise RuntimeError("whisper CLI not found. Install with: pip install openai-whisper")

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Download audio only
        audio_path = f"{tmp_dir}/{video_id}.%(ext)s"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": audio_path,
            "quiet": True,
            "no_warnings": True,
            "cookiesfrombrowser": ("chrome",),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        meta = VideoMeta(
            video_id=video_id,
            title=info.get("title"),
            channel=info.get("channel") or info.get("uploader"),
            duration_seconds=info.get("duration"),
            upload_date=info.get("upload_date"),
            description=info.get("description"),
        )

        audio_file = f"{tmp_dir}/{video_id}.mp3"

        # Run whisper CLI
        result = subprocess.run(
            [
                whisper_bin,
                audio_file,
                "--model",
                whisper_model,
                "--language",
                lang,
                "--output_format",
                "json",
                "--output_dir",
                tmp_dir,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Whisper failed: {result.stderr[:500]}")

        # Parse whisper JSON output
        json_file = f"{tmp_dir}/{video_id}.json"
        with open(json_file) as f:
            whisper_data = _json.load(f)

    segments = whisper_data.get("segments", [])
    snippets = [
        TranscriptSnippet(
            text=seg["text"].strip(),
            start=seg["start"],
            duration=seg["end"] - seg["start"],
        )
        for seg in segments
        if seg.get("text", "").strip()
    ]

    return TranscriptResult(
        meta=meta,
        snippets=snippets,
        source=TranscriptSource.WHISPER,
        language=lang,
        is_generated=True,
    )


# ---------------------------------------------------------------------------
# Metadata Enrichment
# ---------------------------------------------------------------------------


def enrich_metadata(result: TranscriptResult) -> TranscriptResult:
    """If metadata is sparse (e.g., from ytt), enrich via yt-dlp."""
    if result.meta.title:
        return result

    try:
        _youtube_throttle()
        import yt_dlp

        url = f"https://www.youtube.com/watch?v={result.meta.video_id}"
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        result.meta.title = info.get("title")
        result.meta.channel = info.get("channel") or info.get("uploader")
        result.meta.duration_seconds = info.get("duration")
        result.meta.upload_date = info.get("upload_date")
        result.meta.description = info.get("description")
    except Exception as e:
        print(f"  [warn] Metadata enrichment failed: {e}", file=sys.stderr)

    return result


# ---------------------------------------------------------------------------
# Fallback Chain Orchestrator
# ---------------------------------------------------------------------------


def list_available_languages(video_id: str) -> list[dict[str, str]]:
    """List available transcript languages for a video.

    Returns list of dicts with 'code', 'name', and 'is_generated' keys.
    """
    _youtube_throttle()
    from youtube_transcript_api import YouTubeTranscriptApi

    ytt = YouTubeTranscriptApi()
    transcript_list = ytt.list(video_id)

    languages = []
    for t in transcript_list:
        languages.append(
            {
                "code": t.language_code,
                "name": t.language,
                "is_generated": t.is_generated,
                "translatable": bool(t.translation_languages),
            }
        )
    return languages


def fetch_transcript(
    video_id: str,
    lang: str = "en",
    translate_to: str | None = None,
    enrich: bool = True,
    whisper: bool = False,
    whisper_model: str = "base",
    verbose: bool = True,
) -> TranscriptResult:
    """Fetch transcript using fallback chain.

    Order:
        1. youtube-transcript-api (fast, lightweight; supports translation)
        2. yt-dlp (heavier, broader compatibility; limited translation)
        3. Whisper (downloads audio + local transcription; opt-in or auto-fallback)

    Args:
        video_id: YouTube video ID.
        lang: Preferred source transcript language.
        translate_to: If set, translate transcript to this language code.
        enrich: Enrich metadata via yt-dlp if sparse.
        whisper: If True, include Whisper in the fallback chain.
        whisper_model: Whisper model size (tiny/base/small/medium/large).
        verbose: Print progress to stderr.
    """
    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)
    errors: list[str] = []
    n_strategies = 3 if whisper else 2

    if translate_to:
        log(f"  [info] Translation requested: {lang} -> {translate_to}")

    # Strategy 1
    try:
        log(f"  [1/{n_strategies}] Trying youtube-transcript-api...")
        result = fetch_via_ytt(video_id, lang, translate_to=translate_to)
        if result.snippets:
            log(f"  [ok]  Got {len(result.snippets)} snippets via youtube-transcript-api")
            if result.translated_from:
                log(f"  [ok]  Translated from {result.translated_from} to {result.language}")
            if enrich:
                result = enrich_metadata(result)
            return result
    except Exception as e:
        errors.append(f"youtube-transcript-api: {e}")
        log(f"  [fail] youtube-transcript-api: {e}")

    # Strategy 2
    try:
        log(f"  [2/{n_strategies}] Trying yt-dlp...")
        result = fetch_via_ytdlp(video_id, lang, translate_to=translate_to)
        if result.snippets:
            log(f"  [ok]  Got {len(result.snippets)} snippets via yt-dlp")
            return result
    except Exception as e:
        errors.append(f"yt-dlp: {e}")
        log(f"  [fail] yt-dlp: {e}")

    # Strategy 3: Whisper (opt-in)
    if whisper:
        try:
            log(f"  [3/{n_strategies}] Trying Whisper ({whisper_model})...")
            result = fetch_via_whisper(video_id, lang, whisper_model=whisper_model)
            if result.snippets:
                log(f"  [ok]  Got {len(result.snippets)} segments via Whisper")
                return result
        except Exception as e:
            errors.append(f"whisper: {e}")
            log(f"  [fail] whisper: {e}")

    raise RuntimeError(
        f"All transcript extraction methods failed for {video_id}:\n"
        + "\n".join(f"  - {err}" for err in errors)
    )
