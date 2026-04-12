"""Tests for Viewfinder SQLite storage layer."""

import pytest

from viewfinder.models import (
    Screenshot,
    ScreenshotResult,
    SummaryResult,
    TranscriptResult,
    TranscriptSnippet,
    TranscriptSource,
    VideoMeta,
)
from viewfinder.storage import Storage


@pytest.fixture
def store(tmp_path):
    """Create a storage instance using a temp database."""
    db_path = tmp_path / "test.db"
    s = Storage(db_path=db_path)
    yield s
    s.close()


def _make_meta(video_id="test123"):
    return VideoMeta(
        video_id=video_id,
        title="Test Video",
        channel="TestChan",
        duration_seconds=120,
    )


def _make_transcript(video_id="test123", language="en"):
    meta = _make_meta(video_id)
    snippets = [
        TranscriptSnippet(text="Hello world", start=0.0, duration=2.5),
        TranscriptSnippet(text="Second segment", start=2.5, duration=3.0),
    ]
    return TranscriptResult(meta=meta, snippets=snippets, language=language)


def _make_summary(transcript=None):
    if transcript is None:
        transcript = _make_transcript()
    return SummaryResult(
        transcript=transcript,
        summary="This is a summary.",
        model="claude-sonnet-4-20250514",
        prompt_template="default",
        input_tokens=500,
        output_tokens=200,
    )


class TestVideoStorage:
    def test_save_and_get(self, store):
        meta = _make_meta()
        store.save_video(meta)
        result = store.get_video("test123")
        assert result is not None
        assert result.title == "Test Video"
        assert result.channel == "TestChan"

    def test_get_missing(self, store):
        assert store.get_video("nonexistent") is None

    def test_upsert_preserves_existing(self, store):
        store.save_video(_make_meta())
        # Save again with sparse data -- should preserve title
        store.save_video(VideoMeta(video_id="test123"))
        result = store.get_video("test123")
        assert result.title == "Test Video"

    def test_video_count(self, store):
        assert store.video_count() == 0
        store.save_video(_make_meta("vid1"))
        store.save_video(_make_meta("vid2"))
        assert store.video_count() == 2


class TestTranscriptStorage:
    def test_save_and_get(self, store):
        transcript = _make_transcript()
        store.save_transcript(transcript)
        result = store.get_transcript("test123", language="en")
        assert result is not None
        assert result.word_count == 4
        assert len(result.snippets) == 2
        assert result.source == TranscriptSource.YTT_API

    def test_has_transcript(self, store):
        assert not store.has_transcript("test123")
        store.save_transcript(_make_transcript())
        assert store.has_transcript("test123")
        assert not store.has_transcript("test123", language="es")

    def test_multiple_languages(self, store):
        store.save_transcript(_make_transcript(language="en"))
        store.save_transcript(_make_transcript(language="es"))
        assert store.has_transcript("test123", language="en")
        assert store.has_transcript("test123", language="es")

    def test_get_missing(self, store):
        assert store.get_transcript("nonexistent") is None

    def test_upsert_updates_content(self, store):
        t1 = _make_transcript()
        store.save_transcript(t1)
        # Make a new transcript with different content
        t2 = _make_transcript()
        t2.snippets = [TranscriptSnippet(text="Updated content", start=0.0, duration=1.0)]
        store.save_transcript(t2)
        result = store.get_transcript("test123")
        assert result.full_text == "Updated content"


class TestSummaryStorage:
    def test_save_and_get(self, store):
        transcript = _make_transcript()
        tid = store.save_transcript(transcript)
        summary = _make_summary(transcript)
        store.save_summary(summary, tid)
        summaries = store.get_summaries("test123")
        assert len(summaries) == 1
        assert summaries[0]["model"] == "claude-sonnet-4-20250514"
        assert summaries[0]["input_tokens"] == 500

    def test_multiple_summaries(self, store):
        transcript = _make_transcript()
        tid = store.save_transcript(transcript)
        store.save_summary(_make_summary(transcript), tid)
        store.save_summary(_make_summary(transcript), tid)
        assert len(store.get_summaries("test123")) == 2


class TestScreenshotStorage:
    def test_save(self, store):
        meta = _make_meta()
        screenshots = ScreenshotResult(
            meta=meta,
            screenshots=[
                Screenshot(path="/tmp/f1.jpg", timestamp=0.0),
                Screenshot(path="/tmp/f2.jpg", timestamp=30.0),
            ],
            interval_seconds=30,
            output_dir="/tmp/screenshots",
        )
        sid = store.save_screenshots(screenshots)
        assert sid > 0


class TestCostTracking:
    def test_empty(self, store):
        summary = store.get_cost_summary()
        assert summary["total_summaries"] == 0
        assert summary["total_tokens"] == 0

    def test_with_data(self, store):
        transcript = _make_transcript()
        tid = store.save_transcript(transcript)
        store.save_summary(_make_summary(transcript), tid)
        summary = store.get_cost_summary()
        assert summary["total_summaries"] == 1
        assert summary["total_input_tokens"] == 500
        assert summary["total_output_tokens"] == 200
        assert summary["total_tokens"] == 700

    def test_by_model(self, store):
        transcript = _make_transcript()
        tid = store.save_transcript(transcript)
        store.save_summary(_make_summary(transcript), tid)
        by_model = store.get_cost_by_model()
        assert len(by_model) == 1
        assert by_model[0]["model"] == "claude-sonnet-4-20250514"
        assert by_model[0]["count"] == 1


class TestListVideos:
    def test_empty(self, store):
        assert store.list_videos() == []

    def test_with_data(self, store):
        transcript = _make_transcript()
        store.save_transcript(transcript)
        videos = store.list_videos()
        assert len(videos) == 1
        assert videos[0]["video_id"] == "test123"
        assert videos[0]["transcript_count"] == 1


class TestContextManager:
    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "ctx_test.db"
        with Storage(db_path=db_path) as s:
            s.save_video(_make_meta())
            assert s.get_video("test123") is not None
