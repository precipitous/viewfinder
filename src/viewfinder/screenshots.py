"""Screenshot extraction from YouTube videos using yt-dlp + ffmpeg.

Downloads the video (or uses a cached copy) and extracts frames at
configurable intervals. Requires ffmpeg to be installed on the system.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .models import Screenshot, ScreenshotResult, VideoMeta


def _check_ffmpeg() -> str:
    """Return path to ffmpeg binary or raise."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "ffmpeg not found. Install it with: sudo apt install ffmpeg (Linux) "
            "or brew install ffmpeg (macOS)"
        )
    return path


def _get_video_duration_ffprobe(video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            import json

            info = json.loads(result.stdout)
            return float(info["format"]["duration"])
    except (subprocess.TimeoutExpired, KeyError, ValueError):
        pass
    return None


def download_video(
    video_id: str,
    output_dir: str,
    verbose: bool = True,
) -> str:
    """Download video using yt-dlp. Returns path to downloaded file."""
    import yt_dlp

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = str(Path(output_dir) / f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": "best[height<=720]/best",  # cap at 720p to save bandwidth
        "outtmpl": output_template,
        "quiet": not verbose,
        "no_warnings": True,
    }

    log(f"  [dl] Downloading video {video_id}...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    log(f"  [dl] Saved to {filename}")
    return filename


def extract_frames(
    video_path: str,
    output_dir: str,
    interval: int = 30,
    verbose: bool = True,
) -> list[Screenshot]:
    """Extract frames from a video at regular intervals using ffmpeg.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to save screenshots.
        interval: Seconds between each screenshot.
        verbose: Print progress to stderr.

    Returns:
        List of Screenshot objects with paths and timestamps.
    """
    ffmpeg = _check_ffmpeg()
    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Get duration to know how many frames we'll get
    duration = _get_video_duration_ffprobe(video_path)
    if duration:
        expected = int(duration // interval) + 1
        log(f"  [ffmpeg] ~{expected} frames every {interval}s from {duration:.0f}s video")
    else:
        log(f"  [ffmpeg] Extracting frames every {interval}s...")

    # Use ffmpeg to extract frames at intervals
    # -vf fps=1/N extracts one frame every N seconds
    output_pattern = str(Path(output_dir) / "frame_%04d.jpg")

    cmd = [
        ffmpeg,
        "-i",
        video_path,
        "-vf",
        f"fps=1/{interval}",
        "-q:v",
        "2",  # high quality JPEG
        "-y",  # overwrite
        output_pattern,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,  # 10 minute timeout
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")

    # Collect generated screenshots
    screenshots = []
    frame_dir = Path(output_dir)
    for frame_path in sorted(frame_dir.glob("frame_*.jpg")):
        # Frame number is 1-indexed; frame_0001.jpg is at t=0
        frame_num = int(frame_path.stem.split("_")[1])
        timestamp = (frame_num - 1) * interval
        screenshots.append(Screenshot(path=str(frame_path), timestamp=float(timestamp)))

    log(f"  [ffmpeg] Extracted {len(screenshots)} screenshots")
    return screenshots


def capture_screenshots(
    video_id: str,
    output_dir: str,
    interval: int = 30,
    meta: VideoMeta | None = None,
    keep_video: bool = False,
    verbose: bool = True,
) -> ScreenshotResult:
    """Full pipeline: download video, extract frames, return result.

    Args:
        video_id: YouTube video ID.
        output_dir: Directory to save screenshots.
        interval: Seconds between screenshots.
        meta: Pre-existing VideoMeta (avoids redundant yt-dlp metadata call).
        keep_video: If True, keep the downloaded video file.
        verbose: Print progress to stderr.

    Returns:
        ScreenshotResult with screenshot paths and metadata.
    """
    _check_ffmpeg()
    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    screenshot_dir = str(Path(output_dir) / "screenshots" / video_id)
    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)

    # Download to a temp dir, or to the output dir if keeping
    if keep_video:
        dl_dir = str(Path(output_dir) / "videos")
        Path(dl_dir).mkdir(parents=True, exist_ok=True)
        video_path = download_video(video_id, dl_dir, verbose=verbose)
        screenshots = extract_frames(video_path, screenshot_dir, interval, verbose=verbose)
    else:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = download_video(video_id, tmp_dir, verbose=verbose)
            screenshots = extract_frames(video_path, screenshot_dir, interval, verbose=verbose)

    if meta is None:
        meta = VideoMeta(video_id=video_id)

    result = ScreenshotResult(
        meta=meta,
        screenshots=screenshots,
        interval_seconds=interval,
        output_dir=screenshot_dir,
    )

    log(f"  [done] {len(screenshots)} screenshots in {screenshot_dir}")
    return result
