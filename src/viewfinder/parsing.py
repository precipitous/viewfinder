"""YouTube URL and video ID parsing."""

import re


def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video ID from various URL formats or bare ID.

    Supports:
        - Bare 11-char IDs
        - youtube.com/watch?v=...
        - youtu.be/...
        - youtube.com/embed/...
        - youtube.com/shorts/...
        - youtube.com/live/...
        - youtube.com/v/...
        - URLs with extra query params (&t=120, &list=..., etc.)
    """
    url_or_id = url_or_id.strip()

    # Already a bare ID (11 chars, alphanumeric + _ -)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id

    patterns = [
        r"(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/v/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/live/)([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    raise ValueError(f"Could not extract video ID from: {url_or_id}")
