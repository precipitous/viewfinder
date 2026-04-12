"""Tests for Viewfinder data models."""

from viewfinder.models import (
    IngestResult,
    Screenshot,
    ScreenshotResult,
    TranscriptResult,
    TranscriptSnippet,
    VideoMeta,
)


class TestVideoMeta:
    def test_auto_url(self):
        meta = VideoMeta(video_id="abc12345678")
        assert meta.url == "https://www.youtube.com/watch?v=abc12345678"

    def test_explicit_url(self):
        meta = VideoMeta(video_id="abc12345678", url="https://custom.url")
        assert meta.url == "https://custom.url"


class TestTranscriptResult:
    def _make_result(self):
        meta = VideoMeta(video_id="test123", title="Test", channel="TestChan")
        snippets = [
            TranscriptSnippet(text="Hello world", start=0.0, duration=2.5),
            TranscriptSnippet(text="This is a test", start=2.5, duration=3.0),
            TranscriptSnippet(text="Third segment here", start=5.5, duration=2.0),
        ]
        return TranscriptResult(meta=meta, snippets=snippets)

    def test_full_text(self):
        result = self._make_result()
        assert result.full_text == "Hello world This is a test Third segment here"

    def test_word_count(self):
        result = self._make_result()
        assert result.word_count == 9

    def test_char_count(self):
        result = self._make_result()
        assert result.char_count == len("Hello world This is a test Third segment here")

    def test_empty_snippets(self):
        result = TranscriptResult(meta=VideoMeta(video_id="empty"))
        assert result.full_text == ""
        assert result.word_count == 0

    def test_to_dict(self):
        result = self._make_result()
        d = result.to_dict()
        assert "word_count" in d
        assert "char_count" in d
        assert d["word_count"] == 9

    def test_translated_from(self):
        result = self._make_result()
        result.translated_from = "en"
        result.language = "es"
        d = result.to_dict()
        assert d["translated_from"] == "en"
        assert d["language"] == "es"

    def test_translated_from_default_none(self):
        result = self._make_result()
        assert result.translated_from is None


class TestIngestResult:
    def test_transcript_only(self):
        meta = VideoMeta(video_id="test123", title="Test")
        transcript = TranscriptResult(meta=meta)
        ingest = IngestResult(transcript=transcript)
        d = ingest.to_dict()
        assert "transcript" in d
        assert "screenshots" not in d
        assert "summary" not in d

    def test_with_screenshots(self):
        meta = VideoMeta(video_id="test123", title="Test")
        transcript = TranscriptResult(meta=meta)
        screenshots = ScreenshotResult(
            meta=meta,
            screenshots=[Screenshot(path="/tmp/f.jpg", timestamp=0.0)],
        )
        ingest = IngestResult(transcript=transcript, screenshots=screenshots)
        d = ingest.to_dict()
        assert d["screenshots"]["count"] == 1
