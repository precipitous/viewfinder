"""Tests for Viewfinder URL parsing."""

import pytest

from viewfinder.parsing import extract_video_id


class TestExtractVideoId:
    """Test YouTube URL and ID parsing."""

    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            # With extra params
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz", "dQw4w9WgXcQ"),
            # Whitespace handling
            ("  dQw4w9WgXcQ  ", "dQw4w9WgXcQ"),
        ],
    )
    def test_valid_urls(self, input_val, expected):
        assert extract_video_id(input_val) == expected

    @pytest.mark.parametrize(
        "input_val",
        [
            "",
            "not-a-url",
            "https://google.com",
            "https://youtube.com/",
            "abc",  # too short for bare ID
        ],
    )
    def test_invalid_urls(self, input_val):
        with pytest.raises(ValueError):
            extract_video_id(input_val)
