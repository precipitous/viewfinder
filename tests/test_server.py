"""Tests for Viewfinder FastAPI server."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from viewfinder.models import TranscriptResult, TranscriptSnippet, TranscriptSource, VideoMeta
from viewfinder.server import app, get_store
from viewfinder.storage import Storage


@pytest.fixture
def store(tmp_path):
    """Create a storage instance with test data."""
    db_path = tmp_path / "test_server.db"
    s = Storage(db_path=db_path)

    # Seed test data
    meta = VideoMeta(
        video_id="test123",
        title="Test Video",
        channel="TestChan",
        duration_seconds=120,
    )
    transcript = TranscriptResult(
        meta=meta,
        snippets=[
            TranscriptSnippet(text="Hello world this is a test", start=0.0, duration=2.5),
            TranscriptSnippet(text="Second segment about Python", start=2.5, duration=3.0),
        ],
        source=TranscriptSource.YTT_API,
        language="en",
    )
    s.save_transcript(transcript)
    yield s
    s.close()


@pytest.fixture
def client(store):
    """Create a test client with injected storage."""

    def _get_store():
        return store

    app.dependency_overrides[get_store] = _get_store

    # Patch the module-level _store
    with (
        patch("viewfinder.server._store", store),
        patch("viewfinder.server.get_store", return_value=store),
        TestClient(app) as c,
    ):
        yield c

    app.dependency_overrides.clear()


class TestListVideos:
    def test_returns_videos(self, client):
        resp = client.get("/api/videos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["video_id"] == "test123"
        assert data[0]["title"] == "Test Video"
        assert data[0]["transcript_count"] == 1


class TestGetVideo:
    def test_found(self, client):
        resp = client.get("/api/videos/test123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Video"
        assert data["transcript"]["word_count"] > 0
        assert data["transcript"]["language"] == "en"

    def test_not_found(self, client):
        resp = client.get("/api/videos/nonexistent")
        assert resp.status_code == 404


class TestGetTranscript:
    def test_found(self, client):
        resp = client.get("/api/videos/test123/transcript")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["snippets"]) == 2
        assert data["word_count"] > 0

    def test_not_found(self, client):
        resp = client.get("/api/videos/nonexistent/transcript")
        assert resp.status_code == 404


class TestSearch:
    def test_finds_results(self, client):
        resp = client.get("/api/search?q=Python")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["video_id"] == "test123"

    def test_no_results(self, client):
        resp = client.get("/api/search?q=xyznonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_requires_query(self, client):
        resp = client.get("/api/search")
        assert resp.status_code == 422


class TestCostReport:
    def test_empty(self, client):
        resp = client.get("/api/cost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_summaries"] == 0


class TestExportMarkdown:
    def test_export(self, client):
        resp = client.get("/api/videos/test123/export.md")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "Test Video" in resp.text
        assert "Hello world" in resp.text

    def test_not_found(self, client):
        resp = client.get("/api/videos/nonexistent/export.md")
        assert resp.status_code == 404


class TestIndex:
    def test_serves_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Viewfinder" in resp.text
        assert "<html" in resp.text
