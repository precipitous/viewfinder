"""Integration tests for Viewfinder (require network access).

These tests hit the real YouTube API and may fail from cloud IPs where
YouTube throttles or blocks requests. Run with:

    pytest -m network

Skip with:

    pytest -m "not network"

Test videos:
    - "Me at the zoo" (jNQXAC9IVRw) -- first YouTube video, short, stable
    - "Do schools kill creativity?" (iG9CE55wbtY) -- TED talk, 65 languages,
      translatable captions, very stable
"""

import pytest

from viewfinder.models import TranscriptSource
from viewfinder.parsing import extract_video_id
from viewfinder.transcript import (
    fetch_transcript,
    fetch_via_ytdlp,
    fetch_via_ytt,
    list_available_languages,
)

# First YouTube video ever uploaded -- unlikely to be removed
TEST_VIDEO_ID = "jNQXAC9IVRw"
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

# TED talk with 65+ languages and translatable captions
TEST_TRANSLATABLE_ID = "iG9CE55wbtY"


# ---------------------------------------------------------------------------
# youtube-transcript-api tests
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestFetchViaYtt:
    def test_basic_fetch(self):
        result = fetch_via_ytt(TEST_VIDEO_ID)
        assert result.snippets
        assert result.source == TranscriptSource.YTT_API
        assert result.meta.video_id == TEST_VIDEO_ID
        assert result.word_count > 0

    def test_language_code(self):
        result = fetch_via_ytt(TEST_VIDEO_ID, lang="en")
        assert result.language == "en"

    def test_translation(self):
        result = fetch_via_ytt(TEST_TRANSLATABLE_ID, translate_to="es")
        assert result.language == "es"
        assert result.translated_from is not None
        assert result.snippets
        assert result.word_count > 0


# ---------------------------------------------------------------------------
# yt-dlp tests
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestFetchViaYtdlp:
    def test_basic_fetch(self):
        result = fetch_via_ytdlp(TEST_VIDEO_ID)
        assert result.snippets
        assert result.source == TranscriptSource.YT_DLP
        assert result.meta.video_id == TEST_VIDEO_ID
        assert result.word_count > 0

    def test_metadata_populated(self):
        result = fetch_via_ytdlp(TEST_VIDEO_ID)
        assert result.meta.title is not None
        assert result.meta.channel is not None
        assert result.meta.duration_seconds is not None


# ---------------------------------------------------------------------------
# Fallback chain tests
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestFetchTranscript:
    def test_basic_fetch(self):
        result = fetch_transcript(TEST_VIDEO_ID, verbose=False)
        assert result.snippets
        assert result.word_count > 0
        assert result.meta.video_id == TEST_VIDEO_ID

    def test_with_enrichment(self):
        result = fetch_transcript(TEST_VIDEO_ID, enrich=True, verbose=False)
        assert result.meta.title is not None
        assert result.meta.channel is not None

    def test_without_enrichment(self):
        """ytt alone gives no metadata; verify enrich=False leaves it sparse."""
        result = fetch_via_ytt(TEST_VIDEO_ID)
        # ytt doesn't populate title
        assert result.meta.title is None

    def test_translation_through_chain(self):
        result = fetch_transcript(TEST_TRANSLATABLE_ID, translate_to="fr", verbose=False)
        assert result.language == "fr"
        assert result.snippets
        assert result.word_count > 0

    def test_url_to_transcript(self):
        """Full pipeline: URL -> parse -> fetch."""
        video_id = extract_video_id(TEST_VIDEO_URL)
        result = fetch_transcript(video_id, verbose=False)
        assert result.snippets


# ---------------------------------------------------------------------------
# Language listing
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestListLanguages:
    def test_lists_languages(self):
        languages = list_available_languages(TEST_VIDEO_ID)
        assert len(languages) > 0
        codes = [lang["code"] for lang in languages]
        assert "en" in codes

    def test_language_dict_shape(self):
        languages = list_available_languages(TEST_VIDEO_ID)
        lang = languages[0]
        assert "code" in lang
        assert "name" in lang
        assert "is_generated" in lang
        assert "translatable" in lang

    def test_translatable_video_has_many_languages(self):
        languages = list_available_languages(TEST_TRANSLATABLE_ID)
        assert len(languages) > 10
        translatable = [lang for lang in languages if lang["translatable"]]
        assert len(translatable) > 0
