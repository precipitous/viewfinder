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
import urllib.request

from .models import TranscriptResult, TranscriptSnippet, TranscriptSource, VideoMeta

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
    """Fallback method: yt-dlp subtitle extraction + metadata.

    Note: yt-dlp does not support translation directly. If translate_to is
    requested, we fetch the available transcript and note that translation
    was not possible via this method (the caller can try ytt first).
    """
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"

    # If translation is requested, also request subs in the target language
    sub_langs = [lang, "en"]
    if translate_to and translate_to not in sub_langs:
        sub_langs.insert(0, translate_to)

    ydl_opts = {
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitleslangs": sub_langs,
        "subtitlesformat": "json3",
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    meta = VideoMeta(
        video_id=video_id,
        title=info.get("title"),
        channel=info.get("channel") or info.get("uploader"),
        duration_seconds=info.get("duration"),
        upload_date=info.get("upload_date"),
        description=info.get("description"),
    )

    # Prefer manual subs; fall back to auto-generated
    subtitles = info.get("subtitles", {})
    auto_captions = info.get("automatic_captions", {})
    is_generated = False
    sub_data = None
    chosen_lang = lang

    # Build language priority: translate_to first (if available), then original lang, then en
    lang_priority = [lang, "en"]
    if translate_to and translate_to not in lang_priority:
        lang_priority.insert(0, translate_to)

    for source, gen_flag in [(subtitles, False), (auto_captions, True)]:
        if sub_data:
            break
        for try_lang in lang_priority:
            if try_lang in source:
                for fmt in source[try_lang]:
                    if fmt.get("ext") == "json3":
                        sub_data = fmt
                        chosen_lang = try_lang
                        is_generated = gen_flag
                        break
                if sub_data:
                    break

    if not sub_data:
        raise RuntimeError(f"No subtitles found via yt-dlp for {video_id}")

    # Fetch actual subtitle content
    sub_url = sub_data["url"]
    with urllib.request.urlopen(sub_url) as resp:
        sub_json = json.loads(resp.read().decode("utf-8"))

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
