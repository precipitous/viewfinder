"""Tests for Viewfinder summarization and LLM backends."""

from viewfinder.models import TranscriptResult, TranscriptSnippet, VideoMeta
from viewfinder.summarize import (
    LLMResponse,
    _build_prompt,
    format_duration,
    list_backends,
    list_prompts,
)


def _make_transcript():
    meta = VideoMeta(
        video_id="test123",
        title="Test Video",
        channel="TestChan",
        duration_seconds=120,
    )
    snippets = [
        TranscriptSnippet(text="Hello world", start=0.0, duration=2.5),
    ]
    return TranscriptResult(meta=meta, snippets=snippets)


class TestPrompts:
    def test_list_prompts(self):
        prompts = list_prompts()
        assert "default" in prompts
        assert "brief" in prompts
        assert "detailed" in prompts
        assert "technical" in prompts

    def test_build_prompt(self):
        transcript = _make_transcript()
        prompt = _build_prompt(transcript, "brief")
        assert "Test Video" in prompt
        assert "Hello world" in prompt

    def test_build_prompt_unknown_key_falls_back(self):
        transcript = _make_transcript()
        prompt = _build_prompt(transcript, "nonexistent")
        # Falls back to default template
        assert "Key points" in prompt


class TestFormatDuration:
    def test_none(self):
        assert format_duration(None) == "Unknown"

    def test_zero(self):
        assert format_duration(0) == "Unknown"

    def test_minutes(self):
        assert format_duration(125) == "2m 5s"

    def test_hours(self):
        assert format_duration(3661) == "1h 1m 1s"


class TestBackends:
    def test_list_backends(self):
        backends = list_backends()
        assert "claude" in backends
        assert "openai" in backends


class TestLLMResponse:
    def test_dataclass(self):
        r = LLMResponse(text="hello", model="test-model", input_tokens=10, output_tokens=5)
        assert r.text == "hello"
        assert r.input_tokens == 10

    def test_optional_tokens(self):
        r = LLMResponse(text="hello", model="test-model")
        assert r.input_tokens is None
        assert r.output_tokens is None
