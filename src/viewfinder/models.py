"""Data models for Viewfinder."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TranscriptSource(str, Enum):
    YTT_API = "youtube-transcript-api"
    YT_DLP = "yt-dlp"
    WHISPER = "whisper"
    MANUAL = "manual"


@dataclass
class TranscriptSnippet:
    text: str
    start: float
    duration: float


@dataclass
class VideoMeta:
    video_id: str
    title: str | None = None
    channel: str | None = None
    duration_seconds: int | None = None
    upload_date: str | None = None
    description: str | None = None
    url: str = ""

    def __post_init__(self):
        if not self.url:
            self.url = f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class TranscriptResult:
    meta: VideoMeta
    snippets: list[TranscriptSnippet] = field(default_factory=list)
    source: TranscriptSource = TranscriptSource.YTT_API
    language: str = "en"
    translated_from: str | None = None
    is_generated: bool = False
    fetched_at: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.snippets)

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())

    @property
    def char_count(self) -> int:
        return len(self.full_text)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["word_count"] = self.word_count
        d["char_count"] = self.char_count
        return d


@dataclass
class Screenshot:
    path: str
    timestamp: float

    @property
    def timestamp_str(self) -> str:
        h, rem = divmod(int(self.timestamp), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass
class ScreenshotResult:
    meta: VideoMeta
    screenshots: list[Screenshot] = field(default_factory=list)
    interval_seconds: int = 30
    output_dir: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["count"] = len(self.screenshots)
        return d


@dataclass
class SummaryResult:
    transcript: TranscriptResult
    summary: str
    model: str
    prompt_template: str
    generated_at: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        # Swap full snippets for counts to keep output manageable
        d["transcript"].pop("snippets", None)
        d["transcript"]["word_count"] = self.transcript.word_count
        d["transcript"]["char_count"] = self.transcript.char_count
        return d


@dataclass
class IngestResult:
    """Combined result of transcript + screenshots for LLM consumption."""

    transcript: TranscriptResult
    screenshots: ScreenshotResult | None = None
    summary: SummaryResult | None = None

    def to_dict(self) -> dict:
        d = {"transcript": self.transcript.to_dict()}
        if self.screenshots:
            d["screenshots"] = self.screenshots.to_dict()
        if self.summary:
            d["summary"] = self.summary.to_dict()
        return d
