"""Tests for Viewfinder output formatters."""

import json

from viewfinder.formatters import (
    to_ingest_markdown,
    to_json,
    to_markdown,
    to_screenshot_text,
    to_transcript_text,
)
from viewfinder.models import (
    IngestResult,
    Screenshot,
    ScreenshotResult,
    SummaryResult,
    TranscriptResult,
    TranscriptSnippet,
    VideoMeta,
)


def _make_transcript():
    meta = VideoMeta(
        video_id="test123",
        title="Test Video",
        channel="TestChan",
        duration_seconds=3661,
    )
    snippets = [
        TranscriptSnippet(text="Hello world", start=0.0, duration=2.5),
        TranscriptSnippet(text="Second segment", start=65.0, duration=3.0),
    ]
    return TranscriptResult(meta=meta, snippets=snippets)


def _make_translated_transcript():
    t = _make_transcript()
    t.language = "es"
    t.translated_from = "en"
    return t


def _make_summary():
    return SummaryResult(
        transcript=_make_transcript(),
        summary="This is a test summary.",
        model="claude-sonnet-4-20250514",
        prompt_template="default",
        input_tokens=100,
        output_tokens=50,
    )


def _make_screenshots():
    meta = VideoMeta(video_id="test123", title="Test Video")
    return ScreenshotResult(
        meta=meta,
        screenshots=[
            Screenshot(path="/tmp/screenshots/frame_0001.jpg", timestamp=0.0),
            Screenshot(path="/tmp/screenshots/frame_0002.jpg", timestamp=30.0),
        ],
        interval_seconds=30,
        output_dir="/tmp/screenshots",
    )


class TestToJson:
    def test_transcript_json(self):
        result = _make_transcript()
        output = to_json(result)
        parsed = json.loads(output)
        assert parsed["meta"]["video_id"] == "test123"

    def test_summary_json(self):
        result = _make_summary()
        output = to_json(result)
        parsed = json.loads(output)
        assert parsed["summary"] == "This is a test summary."
        assert parsed["model"] == "claude-sonnet-4-20250514"

    def test_screenshot_json(self):
        result = _make_screenshots()
        output = to_json(result)
        parsed = json.loads(output)
        assert parsed["count"] == 2
        assert parsed["interval_seconds"] == 30

    def test_ingest_json(self):
        ingest = IngestResult(
            transcript=_make_transcript(),
            screenshots=_make_screenshots(),
        )
        output = to_json(ingest)
        parsed = json.loads(output)
        assert "transcript" in parsed
        assert "screenshots" in parsed


class TestToMarkdown:
    def test_contains_title(self):
        md = to_markdown(_make_summary())
        assert "# Test Video" in md

    def test_contains_summary(self):
        md = to_markdown(_make_summary())
        assert "This is a test summary." in md

    def test_contains_token_counts(self):
        md = to_markdown(_make_summary())
        assert "100" in md
        assert "50" in md

    def test_contains_language(self):
        md = to_markdown(_make_summary())
        assert "**Language:**" in md

    def test_translated_summary_markdown(self):
        summary = SummaryResult(
            transcript=_make_translated_transcript(),
            summary="Translated summary.",
            model="claude-sonnet-4-20250514",
            prompt_template="default",
        )
        md = to_markdown(summary)
        assert "**Translated from:** en" in md


class TestToTranscriptText:
    def test_plain(self):
        text = to_transcript_text(_make_transcript())
        assert text == "Hello world Second segment"

    def test_timestamps(self):
        text = to_transcript_text(_make_transcript(), timestamps=True)
        assert "[00:00:00]" in text
        assert "[00:01:05]" in text
        assert "Hello world" in text

    def test_translated_plain(self):
        text = to_transcript_text(_make_translated_transcript())
        assert "[Translated from en to es]" in text
        assert "Hello world Second segment" in text

    def test_translated_timestamps(self):
        text = to_transcript_text(_make_translated_transcript(), timestamps=True)
        assert "[Translated from en to es]" in text
        assert "[00:00:00]" in text


class TestToScreenshotText:
    def test_output(self):
        text = to_screenshot_text(_make_screenshots())
        assert "Test Video" in text
        assert "every 30s" in text
        assert "Count: 2" in text
        assert "frame_0001.jpg" in text


class TestToIngestMarkdown:
    def test_transcript_and_screenshots(self):
        ingest = IngestResult(
            transcript=_make_transcript(),
            screenshots=_make_screenshots(),
        )
        md = to_ingest_markdown(ingest)
        assert "# Test Video" in md
        assert "## Screenshots" in md
        assert "## Transcript" in md
        assert "frame_0001.jpg" in md
        assert "Hello world" in md

    def test_transcript_only(self):
        ingest = IngestResult(transcript=_make_transcript())
        md = to_ingest_markdown(ingest)
        assert "## Transcript" in md
        assert "## Screenshots" not in md

    def test_with_summary(self):
        ingest = IngestResult(
            transcript=_make_transcript(),
            summary=_make_summary(),
        )
        md = to_ingest_markdown(ingest)
        assert "## Summary" in md
        assert "This is a test summary." in md
