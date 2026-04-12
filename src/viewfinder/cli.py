"""Viewfinder CLI -- YouTube video ingestion from the command line."""

import argparse
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from .formatters import (
    to_ingest_markdown,
    to_json,
    to_markdown,
    to_screenshot_text,
    to_transcript_text,
)
from .models import IngestResult
from .parsing import extract_video_id
from .summarize import PROMPTS, summarize
from .transcript import fetch_transcript


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="viewfinder",
        description="Viewfinder -- YouTube video ingestion engine. "
        "Extract transcripts, capture screenshots, and generate AI summaries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              # Transcript only (no API key needed)
              viewfinder https://youtube.com/watch?v=VIDEO_ID --transcript-only

              # Translate transcript to Spanish
              viewfinder VIDEO_ID --transcript-only --translate-to es

              # Screenshots every 60 seconds
              viewfinder VIDEO_ID --screenshots --screenshot-interval 60 --output-dir ./out

              # Full ingest: transcript + screenshots + summary
              viewfinder VIDEO_URL --screenshots --output-dir ./out

              # Default summary
              viewfinder VIDEO_ID

              # Detailed analysis, markdown output
              viewfinder VIDEO_URL --prompt detailed --format md

              # Brief summary, JSON output
              viewfinder VIDEO_URL --prompt brief --format json

              # Save to directory
              viewfinder VIDEO_URL --output-dir ./summaries

              # Batch mode
              viewfinder --batch urls.txt --output-dir ./summaries

              # Use Haiku for cheaper/faster runs
              viewfinder VIDEO_URL --model claude-haiku-4-5-20251001

              # List available transcript languages
              viewfinder VIDEO_ID --list-languages
        """),
    )

    p.add_argument("video", nargs="?", help="YouTube URL or video ID")
    p.add_argument("--batch", type=str, help="File with one URL/ID per line for batch processing")
    p.add_argument("--lang", default="en", help="Preferred transcript language (default: en)")
    p.add_argument(
        "--translate-to",
        type=str,
        default=None,
        help="Translate transcript to this language code (e.g., es, fr, de, ja)",
    )
    p.add_argument(
        "--list-languages",
        action="store_true",
        help="List available transcript languages for the video and exit",
    )
    p.add_argument(
        "--transcript-only",
        action="store_true",
        help="Extract transcript without summarization",
    )
    p.add_argument(
        "--timestamps", action="store_true", help="Include timestamps in transcript output"
    )

    # Screenshot options
    p.add_argument(
        "--screenshots",
        action="store_true",
        help="Extract screenshots from the video using ffmpeg",
    )
    p.add_argument(
        "--screenshot-interval",
        type=int,
        default=30,
        help="Seconds between screenshots (default: 30)",
    )
    p.add_argument(
        "--keep-video",
        action="store_true",
        help="Keep the downloaded video file after screenshot extraction",
    )

    p.add_argument(
        "--prompt",
        choices=list(PROMPTS.keys()),
        default="default",
        help="Summary prompt template (default: default)",
    )
    p.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Claude model for summarization",
    )
    p.add_argument(
        "--format",
        choices=["json", "md", "text"],
        default="md",
        dest="output_format",
        help="Output format (default: md)",
    )
    p.add_argument("--output-dir", type=str, help="Directory to save output files")
    p.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip metadata enrichment via yt-dlp",
    )
    p.add_argument(
        "--api-key", type=str, help="Anthropic API key (default: ANTHROPIC_API_KEY env var)"
    )
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")

    return p


def process_video(video_input: str, args: argparse.Namespace) -> str:
    """Process a single video. Returns formatted output string."""
    video_id = extract_video_id(video_input)
    verbose = not args.quiet

    if verbose:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"Processing: {video_id}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)

    # Fetch transcript
    transcript = fetch_transcript(
        video_id,
        lang=args.lang,
        translate_to=args.translate_to,
        enrich=not args.no_enrich,
        verbose=verbose,
    )

    if verbose:
        info_parts = [
            f"{transcript.word_count:,} words",
            f"source={transcript.source.value}",
            f"lang={transcript.language}",
            f"generated={transcript.is_generated}",
        ]
        if transcript.translated_from:
            info_parts.append(f"translated_from={transcript.translated_from}")
        print(f"  [info] {', '.join(info_parts)}", file=sys.stderr)

    # Screenshots
    screenshot_result = None
    if args.screenshots:
        from .screenshots import capture_screenshots

        output_dir = args.output_dir or "."
        screenshot_result = capture_screenshots(
            video_id,
            output_dir=output_dir,
            interval=args.screenshot_interval,
            meta=transcript.meta,
            keep_video=args.keep_video,
            verbose=verbose,
        )

    # Transcript-only mode
    if args.transcript_only:
        if args.screenshots and screenshot_result:
            # Return combined ingest result
            ingest = IngestResult(transcript=transcript, screenshots=screenshot_result)
            if args.output_format == "json":
                return to_json(ingest)
            elif args.output_format == "md":
                return to_ingest_markdown(ingest)
            else:
                text = to_transcript_text(transcript, timestamps=args.timestamps)
                text += "\n\n" + to_screenshot_text(screenshot_result)
                return text

        if args.output_format == "json":
            return to_json(transcript)
        return to_transcript_text(transcript, timestamps=args.timestamps)

    # Summarize
    summary = summarize(
        transcript,
        prompt_key=args.prompt,
        model=args.model,
        api_key=args.api_key,
        verbose=verbose,
    )

    if args.screenshots and screenshot_result:
        ingest = IngestResult(transcript=transcript, screenshots=screenshot_result, summary=summary)
        if args.output_format == "json":
            return to_json(ingest)
        elif args.output_format == "md":
            return to_ingest_markdown(ingest)
        else:
            return summary.summary

    if args.output_format == "json":
        return to_json(summary)
    elif args.output_format == "md":
        return to_markdown(summary)
    else:
        return summary.summary


def save_output(content: str, video_id: str, output_dir: str, ext: str):
    """Save output to a file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{video_id}_{timestamp}.{ext}"
    filepath = Path(output_dir) / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"  [saved] {filepath}", file=sys.stderr)


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Handle --list-languages
    if args.list_languages:
        if not args.video:
            print("Error: --list-languages requires a video URL or ID", file=sys.stderr)
            sys.exit(1)
        from .transcript import list_available_languages

        video_id = extract_video_id(args.video)
        languages = list_available_languages(video_id)
        print(f"Available transcripts for {video_id}:")
        for lang in languages:
            gen_tag = " (auto-generated)" if lang["is_generated"] else ""
            trans_tag = " [translatable]" if lang["translatable"] else ""
            print(f"  {lang['code']:>5}  {lang['name']}{gen_tag}{trans_tag}")
        sys.exit(0)

    if not args.video and not args.batch:
        parser.print_help()
        sys.exit(1)

    if args.screenshots and not args.output_dir:
        print(
            "Warning: --screenshots without --output-dir; "
            "screenshots will be saved to ./screenshots/",
            file=sys.stderr,
        )

    # Collect inputs
    videos: list[str] = []
    if args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            print(f"Error: Batch file not found: {args.batch}", file=sys.stderr)
            sys.exit(1)
        videos = [
            line.strip()
            for line in batch_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not args.quiet:
            print(f"Batch mode: {len(videos)} videos to process", file=sys.stderr)
    else:
        videos = [args.video]

    ext_map = {"json": "json", "md": "md", "text": "txt"}
    ext = ext_map[args.output_format]

    for video_input in videos:
        try:
            output = process_video(video_input, args)

            if args.output_dir:
                video_id = extract_video_id(video_input)
                save_output(output, video_id, args.output_dir, ext)
            else:
                print(output)
        except Exception as e:
            print(f"\nError processing {video_input}: {e}", file=sys.stderr)
            if len(videos) == 1:
                sys.exit(1)

    if not args.quiet:
        print(f"\nDone. Processed {len(videos)} video(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
