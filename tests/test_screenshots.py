"""Tests for Viewfinder screenshot extraction."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from viewfinder.models import Screenshot, ScreenshotResult, VideoMeta
from viewfinder.screenshots import _check_ffmpeg, extract_frames


class TestCheckFfmpeg:
    def test_found(self):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            assert _check_ffmpeg() == "/usr/bin/ffmpeg"

    def test_not_found(self):
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="ffmpeg not found"),
        ):
            _check_ffmpeg()


class TestScreenshotModel:
    def test_timestamp_str(self):
        s = Screenshot(path="/tmp/frame_0001.jpg", timestamp=0.0)
        assert s.timestamp_str == "00:00:00"

    def test_timestamp_str_minutes(self):
        s = Screenshot(path="/tmp/frame_0003.jpg", timestamp=65.0)
        assert s.timestamp_str == "00:01:05"

    def test_timestamp_str_hours(self):
        s = Screenshot(path="/tmp/frame.jpg", timestamp=3661.0)
        assert s.timestamp_str == "01:01:01"


class TestScreenshotResult:
    def test_to_dict(self):
        meta = VideoMeta(video_id="test123", title="Test")
        screenshots = [
            Screenshot(path="/tmp/frame_0001.jpg", timestamp=0.0),
            Screenshot(path="/tmp/frame_0002.jpg", timestamp=30.0),
        ]
        result = ScreenshotResult(
            meta=meta,
            screenshots=screenshots,
            interval_seconds=30,
            output_dir="/tmp/screenshots",
        )
        d = result.to_dict()
        assert d["count"] == 2
        assert d["interval_seconds"] == 30
        assert len(d["screenshots"]) == 2

    def test_empty(self):
        result = ScreenshotResult(meta=VideoMeta(video_id="empty"))
        assert result.to_dict()["count"] == 0


class TestExtractFrames:
    def test_extracts_frames(self, tmp_path):
        """Test frame extraction with a mock ffmpeg that creates frame files."""
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_dir = str(tmp_path / "frames")

        # Create fake frame files that ffmpeg would produce
        def fake_ffmpeg_run(cmd, **kwargs):
            frame_dir = Path(output_dir)
            frame_dir.mkdir(parents=True, exist_ok=True)
            for i in range(1, 4):
                (frame_dir / f"frame_{i:04d}.jpg").touch()
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with (
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("subprocess.run", side_effect=fake_ffmpeg_run),
        ):
            screenshots = extract_frames(str(video_path), output_dir, interval=30, verbose=False)

        assert len(screenshots) == 3
        assert screenshots[0].timestamp == 0.0
        assert screenshots[1].timestamp == 30.0
        assert screenshots[2].timestamp == 60.0

    def test_ffmpeg_failure(self, tmp_path):
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_dir = str(tmp_path / "frames")

        def fake_fail(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "Error: bad format")

        with (
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("subprocess.run", side_effect=fake_fail),
            pytest.raises(RuntimeError, match="ffmpeg failed"),
        ):
            extract_frames(str(video_path), output_dir, interval=30, verbose=False)
