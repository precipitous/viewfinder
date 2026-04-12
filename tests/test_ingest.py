"""Tests for Viewfinder bulk ingestion, feeds, webhooks, and rate limiting."""

from unittest.mock import MagicMock, patch

from viewfinder.ingest import (
    RateLimiter,
    fetch_feed_video_ids,
    send_webhook,
)

# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_defaults(self):
        rl = RateLimiter()
        assert rl.delay == 1.0
        assert rl.max_retries == 3
        assert rl.should_retry

    def test_success_resets(self):
        rl = RateLimiter()
        rl.on_failure()
        assert rl._consecutive_failures == 1
        rl.on_success()
        assert rl._consecutive_failures == 0

    def test_backoff_increases(self):
        rl = RateLimiter(delay=1.0, backoff_factor=2.0)
        wait1 = rl.on_failure()
        assert wait1 == 2.0  # 1.0 * 2^1
        wait2 = rl.on_failure()
        assert wait2 == 4.0  # 1.0 * 2^2

    def test_should_retry_exhausted(self):
        rl = RateLimiter(max_retries=2)
        rl.on_failure()
        assert rl.should_retry
        rl.on_failure()
        assert not rl.should_retry

    def test_custom_delay(self):
        rl = RateLimiter(delay=0.5)
        assert rl.delay == 0.5


# ---------------------------------------------------------------------------
# RSS feed parsing
# ---------------------------------------------------------------------------

SAMPLE_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <entry>
    <yt:videoId>abc123def45</yt:videoId>
    <title>Video One</title>
  </entry>
  <entry>
    <yt:videoId>xyz789ghi01</yt:videoId>
    <title>Video Two</title>
  </entry>
  <entry>
    <yt:videoId>mno456pqr23</yt:videoId>
    <title>Video Three</title>
  </entry>
</feed>
"""


class TestFetchFeedVideoIds:
    def test_parses_feed(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_FEED_XML.encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ids = fetch_feed_video_ids("UCtest123", verbose=False)

        assert ids == ["abc123def45", "xyz789ghi01", "mno456pqr23"]

    def test_limit(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_FEED_XML.encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ids = fetch_feed_video_ids("UCtest123", limit=2, verbose=False)

        assert len(ids) == 2
        assert ids == ["abc123def45", "xyz789ghi01"]


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


class TestSendWebhook:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                verbose=False,
            )
        assert result is True

    def test_failure(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            result = send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                verbose=False,
            )
        assert result is False

    def test_non_2xx(self):
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = send_webhook(
                "https://example.com/webhook",
                {"event": "test"},
                verbose=False,
            )
        assert result is False


# ---------------------------------------------------------------------------
# Playlist/channel extraction (mocked yt-dlp)
# ---------------------------------------------------------------------------


class TestExtractPlaylistVideoIds:
    def test_extracts_ids(self):
        from viewfinder.ingest import extract_playlist_video_ids

        mock_info = {
            "entries": [
                {"id": "vid1_abc_def"},
                {"id": "vid2_ghi_jkl"},
                None,  # yt-dlp can include None entries
                {"id": "vid3_mno_pqr"},
            ]
        }

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            url = "https://youtube.com/playlist?list=PLtest"
            ids = extract_playlist_video_ids(url, verbose=False)

        assert len(ids) == 3


class TestExtractChannelVideoIds:
    def test_extracts_ids(self):
        from viewfinder.ingest import extract_channel_video_ids

        mock_info = {
            "entries": [
                {"id": "vid1_abc_def"},
                {"id": "vid2_ghi_jkl"},
            ]
        }

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            ids = extract_channel_video_ids(
                "https://youtube.com/@TestChannel", limit=5, verbose=False
            )

        assert len(ids) == 2
