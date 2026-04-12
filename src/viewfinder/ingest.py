"""Bulk ingestion: playlists, channels, and RSS feeds.

Uses yt-dlp for playlist/channel extraction and stdlib xml.etree for RSS parsing.
"""

import contextlib
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .parsing import extract_video_id

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@dataclass
class RateLimiter:
    """Simple rate limiter with configurable delay and exponential backoff."""

    delay: float = 1.0
    max_retries: int = 3
    backoff_factor: float = 2.0
    _consecutive_failures: int = field(default=0, repr=False)

    def wait(self):
        """Wait the configured delay between requests."""
        if self.delay > 0:
            time.sleep(self.delay)

    def on_success(self):
        self._consecutive_failures = 0

    def on_failure(self) -> float:
        """Record a failure and return the backoff wait time."""
        self._consecutive_failures += 1
        wait = self.delay * (self.backoff_factor**self._consecutive_failures)
        return wait

    @property
    def should_retry(self) -> bool:
        return self._consecutive_failures < self.max_retries


# ---------------------------------------------------------------------------
# Playlist extraction
# ---------------------------------------------------------------------------


def extract_playlist_video_ids(
    playlist_url: str,
    limit: int | None = None,
    verbose: bool = True,
) -> list[str]:
    """Extract all video IDs from a YouTube playlist.

    Args:
        playlist_url: URL to a YouTube playlist.
        limit: Max number of videos to extract (None = all).
        verbose: Print progress to stderr.
    """
    import yt_dlp

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
    }
    if limit:
        ydl_opts["playlistend"] = limit

    log("  [playlist] Extracting video IDs from playlist...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)

    if not info:
        raise RuntimeError(f"Could not extract playlist info from {playlist_url}")

    entries = info.get("entries", [])
    video_ids = []
    for entry in entries:
        if entry is None:
            continue
        vid = entry.get("id") or entry.get("url", "")
        if vid:
            with contextlib.suppress(ValueError):
                vid = extract_video_id(vid)
            video_ids.append(vid)

    log(f"  [playlist] Found {len(video_ids)} videos")
    return video_ids


# ---------------------------------------------------------------------------
# Channel extraction
# ---------------------------------------------------------------------------


def extract_channel_video_ids(
    channel_url: str,
    limit: int = 10,
    verbose: bool = True,
) -> list[str]:
    """Extract latest video IDs from a YouTube channel.

    Args:
        channel_url: URL to a YouTube channel (e.g., youtube.com/@ChannelName).
        limit: Max number of recent videos to extract.
        verbose: Print progress to stderr.
    """
    import yt_dlp

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    # Append /videos to channel URL if it doesn't end with it
    if not channel_url.rstrip("/").endswith("/videos"):
        channel_url = channel_url.rstrip("/") + "/videos"

    ydl_opts = {
        "extract_flat": True,
        "playlistend": limit,
        "quiet": True,
        "no_warnings": True,
    }

    log(f"  [channel] Extracting latest {limit} videos...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    if not info:
        raise RuntimeError(f"Could not extract channel info from {channel_url}")

    entries = info.get("entries", [])
    video_ids = []
    for entry in entries:
        if entry is None:
            continue
        vid = entry.get("id") or entry.get("url", "")
        if vid:
            with contextlib.suppress(ValueError):
                vid = extract_video_id(vid)
            video_ids.append(vid)

    log(f"  [channel] Found {len(video_ids)} videos")
    return video_ids


# ---------------------------------------------------------------------------
# RSS feed parsing
# ---------------------------------------------------------------------------

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def parse_channel_id_from_url(url: str) -> str | None:
    """Try to resolve a channel URL to a channel ID using yt-dlp."""
    import yt_dlp

    ydl_opts = {
        "extract_flat": True,
        "playlistend": 1,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info:
        return info.get("channel_id") or info.get("id")
    return None


def fetch_feed_video_ids(
    channel_id: str,
    limit: int | None = None,
    verbose: bool = True,
) -> list[str]:
    """Fetch recent video IDs from a YouTube channel's RSS feed.

    This is lightweight (no yt-dlp needed) but only returns the last ~15 videos.

    Args:
        channel_id: YouTube channel ID (e.g., UCxxxxxxxx).
        limit: Max videos to return (None = all from feed).
        verbose: Print progress to stderr.
    """
    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    feed_url = YOUTUBE_FEED_URL.format(channel_id=channel_id)
    log(f"  [feed] Fetching RSS feed for channel {channel_id}...")

    with urllib.request.urlopen(feed_url, timeout=30) as resp:
        xml_data = resp.read().decode("utf-8")

    root = ET.fromstring(xml_data)
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

    video_ids = []
    for entry in root.findall("atom:entry", ns):
        vid_el = entry.find("yt:videoId", ns)
        if vid_el is not None and vid_el.text:
            video_ids.append(vid_el.text)

    if limit:
        video_ids = video_ids[:limit]

    log(f"  [feed] Found {len(video_ids)} videos from RSS feed")
    return video_ids


# ---------------------------------------------------------------------------
# Webhook notification
# ---------------------------------------------------------------------------


def send_webhook(
    url: str,
    payload: dict,
    verbose: bool = True,
) -> bool:
    """Send a JSON POST to a webhook URL.

    Args:
        url: The webhook endpoint.
        payload: JSON-serializable dict to send.
        verbose: Print progress to stderr.

    Returns:
        True if the webhook succeeded (2xx), False otherwise.
    """
    import json

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            log(f"  [webhook] POST {url} -> {resp.status}")
            return 200 <= resp.status < 300
    except Exception as e:
        log(f"  [webhook] POST {url} failed: {e}")
        return False
