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
#
# Two backends:
#   - "local"  : faster-whisper on GPU (free, ~2-5 min per hour of audio)
#   - "groq"   : Groq Whisper API (~$0.01/hr, ~10 seconds per hour of audio)
# ---------------------------------------------------------------------------


def _download_audio(video_id: str, tmp_dir: str) -> tuple[str, VideoMeta]:
    """Download audio from YouTube video. Returns (audio_path, metadata)."""
    import yt_dlp

    _youtube_throttle()
    url = f"https://www.youtube.com/watch?v={video_id}"
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
                "preferredquality": "128",
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

    return f"{tmp_dir}/{video_id}.mp3", meta


def _transcribe_local(
    audio_path: str,
    lang: str,
    model_size: str,
    verbose: bool,
) -> list[TranscriptSnippet]:
    """Transcribe audio using faster-whisper locally (GPU or CPU)."""
    from faster_whisper import WhisperModel

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    # Use GPU if available, fall back to CPU
    device = "cuda"
    compute_type = "float16"
    try:
        import ctranslate2

        if not ctranslate2.get_cuda_device_count():
            device = "cpu"
            compute_type = "int8"
    except Exception:
        device = "cpu"
        compute_type = "int8"

    log(f"  [whisper] Loading {model_size} model on {device}...")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    log("  [whisper] Transcribing...")
    segments_iter, info = model.transcribe(audio_path, language=lang)

    snippets = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            dur = seg.end - seg.start
            snippets.append(TranscriptSnippet(text=text, start=seg.start, duration=dur))

    log(f"  [whisper] {len(snippets)} segments, detected language: {info.language}")
    return snippets


def _transcribe_groq(
    audio_path: str,
    lang: str,
    verbose: bool,
) -> list[TranscriptSnippet]:
    """Transcribe audio using Groq's Whisper API (~$0.01/hr)."""
    import os

    import httpx

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set. Get one at https://console.groq.com")

    log("  [groq] Uploading audio to Groq Whisper API...")

    with open(audio_path, "rb") as f:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.split("/")[-1], f, "audio/mpeg")},
            data={
                "model": "whisper-large-v3",
                "response_format": "verbose_json",
                "language": lang,
            },
            timeout=300,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    segments = data.get("segments", [])

    snippets = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if text:
            snippets.append(
                TranscriptSnippet(
                    text=text,
                    start=seg.get("start", 0.0),
                    duration=seg.get("end", 0.0) - seg.get("start", 0.0),
                )
            )

    log(f"  [groq] {len(snippets)} segments transcribed")
    return snippets


def fetch_via_whisper(
    video_id: str,
    lang: str = "en",
    whisper_model: str = "small",
    whisper_backend: str = "local",
    verbose: bool = True,
) -> TranscriptResult:
    """Fallback: download audio, transcribe with Whisper.

    Args:
        video_id: YouTube video ID.
        lang: Language hint for Whisper.
        whisper_model: Model size for local backend (tiny/base/small/medium/large).
        whisper_backend: "local" (faster-whisper on GPU/CPU) or "groq" (cloud API).
        verbose: Print progress to stderr.
    """
    import tempfile

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    with tempfile.TemporaryDirectory() as tmp_dir:
        log(f"  [whisper] Downloading audio for {video_id}...")
        audio_path, meta = _download_audio(video_id, tmp_dir)

        if whisper_backend == "groq":
            snippets = _transcribe_groq(audio_path, lang, verbose)
        else:
            snippets = _transcribe_local(audio_path, lang, whisper_model, verbose)

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


def _correct_transcript_with_llm(
    result: TranscriptResult,
    verbose: bool = True,
) -> TranscriptResult:
    """Use an LLM to fix proper nouns and technical terms in a Whisper transcript.

    Uses the video title, channel, and description as context to correct
    terms that Whisper commonly gets wrong (product names, jargon, etc.).
    Only runs on Whisper-generated transcripts.
    """
    if result.source != TranscriptSource.WHISPER:
        return result

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    title = result.meta.title or ""
    channel = result.meta.channel or ""
    description = (result.meta.description or "")[:500]

    if not title:
        return result

    log("  [correct] Running LLM transcript correction...")

    # Build a focused correction prompt
    full_text = result.full_text
    # Only correct if transcript is manageable size
    if len(full_text) > 100_000:
        log("  [correct] Transcript too long for correction, skipping")
        return result

    prompt = (
        "Fix proper nouns, product names, and technical terms in this transcript. "
        "Use the video title, channel, and description as context for what the "
        "correct spellings should be. Only fix clear errors -- do not rephrase, "
        "summarize, or change the meaning. Return ONLY the corrected transcript "
        "text, nothing else.\n\n"
        f"Video title: {title}\n"
        f"Channel: {channel}\n"
        f"Description: {description}\n\n"
        f"Transcript to correct:\n{full_text}"
    )

    try:
        from .summarize import _call_openai_compat

        # Try local LLM first (R1 / ollama / vLLM)
        response = _call_openai_compat(
            prompt=prompt,
            model="laserbeak-triage-q4",
            max_tokens=len(full_text) + 1000,
            api_key=None,
            base_url="http://localhost:11434",
        )
        corrected_text = response.text.strip()

        if corrected_text and len(corrected_text) > len(full_text) * 0.5:
            # Rebuild snippets with corrected text
            # Simple approach: replace full text in each snippet proportionally
            words_original = full_text.split()
            words_corrected = corrected_text.split()

            if abs(len(words_corrected) - len(words_original)) < len(words_original) * 0.1:
                # Word counts are close enough -- map corrections back to snippets
                idx = 0
                for snippet in result.snippets:
                    orig_words = snippet.text.split()
                    n = len(orig_words)
                    if idx + n <= len(words_corrected):
                        snippet.text = " ".join(words_corrected[idx : idx + n])
                    idx += n
                log(f"  [correct] Transcript corrected ({len(words_corrected)} words)")
            else:
                log("  [correct] Word count mismatch, skipping correction")
        else:
            log("  [correct] LLM returned empty or truncated response, skipping")

    except Exception as e:
        log(f"  [correct] LLM correction failed (non-fatal): {e!s:.100}")

    return result


def fetch_transcript(
    video_id: str,
    lang: str = "en",
    translate_to: str | None = None,
    enrich: bool = True,
    whisper: bool = True,
    whisper_model: str = "small",
    whisper_backend: str = "local",
    correct: bool = True,
    verbose: bool = True,
) -> TranscriptResult:
    """Fetch transcript using fallback chain.

    Order:
        1. youtube-transcript-api (fast, lightweight; supports translation)
        2. yt-dlp (heavier, broader compatibility; limited translation)
        3. Whisper (downloads audio + transcription; opt-in or auto-fallback)

    Args:
        video_id: YouTube video ID.
        lang: Preferred source transcript language.
        translate_to: If set, translate transcript to this language code.
        enrich: Enrich metadata via yt-dlp if sparse.
        whisper: If True, include Whisper in the fallback chain.
        whisper_model: Model size for local Whisper (tiny/base/small/medium/large).
        whisper_backend: "local" (faster-whisper on GPU) or "groq" (cloud, ~$0.01/hr).
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
        backend_label = f"Whisper/{whisper_backend}"
        if whisper_backend == "local":
            backend_label = f"faster-whisper ({whisper_model})"
        elif whisper_backend == "groq":
            backend_label = "Groq Whisper API"
        try:
            log(f"  [3/{n_strategies}] Trying {backend_label}...")
            result = fetch_via_whisper(
                video_id,
                lang,
                whisper_model=whisper_model,
                whisper_backend=whisper_backend,
                verbose=verbose,
            )
            if result.snippets:
                log(f"  [ok]  Got {len(result.snippets)} segments via {backend_label}")
                if correct:
                    result = _correct_transcript_with_llm(result, verbose=verbose)
                return result
        except Exception as e:
            errors.append(f"whisper ({whisper_backend}): {e}")
            log(f"  [fail] {backend_label}: {e}")

    raise RuntimeError(
        f"All transcript extraction methods failed for {video_id}:\n"
        + "\n".join(f"  - {err}" for err in errors)
    )
