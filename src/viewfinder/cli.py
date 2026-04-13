"""Viewfinder CLI -- YouTube video ingestion from the command line."""

import argparse
import sys
import textwrap
import time
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
    p.add_argument("--playlist", type=str, help="YouTube playlist URL to ingest all videos")
    p.add_argument("--channel", type=str, help="YouTube channel URL to ingest latest videos")
    p.add_argument(
        "--channel-limit",
        type=int,
        default=10,
        help="Max videos to fetch from a channel (default: 10)",
    )
    p.add_argument(
        "--feed",
        type=str,
        help="YouTube channel ID for RSS feed monitoring (lightweight, last ~15 videos)",
    )
    p.add_argument(
        "--webhook-url", type=str, help="URL to POST JSON notifications on new summaries"
    )
    p.add_argument(
        "--rate-limit",
        type=float,
        default=2.0,
        help="Seconds between YouTube requests in bulk modes (default: 2.0)",
    )
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

    # Whisper fallback options (on by default)
    p.add_argument(
        "--no-whisper",
        action="store_true",
        help="Disable Whisper fallback (only use YouTube subtitles)",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        help="Use Groq cloud for Whisper (~$0.01/hr) instead of local GPU",
    )
    p.add_argument(
        "--whisper-model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Local Whisper model size (default: small)",
    )
    p.add_argument(
        "--no-correct",
        action="store_true",
        help="Skip LLM transcript correction on Whisper output",
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
        help="Model for summarization (default: claude-sonnet-4-20250514)",
    )
    p.add_argument(
        "--backend",
        choices=["claude", "openai"],
        default="claude",
        help="LLM backend: claude (Anthropic API) or openai (OpenAI-compatible)",
    )
    p.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL for OpenAI-compatible backend (e.g., http://trypticon:8000)",
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

    # Storage / persistence
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip the local DB cache; always fetch fresh from YouTube",
    )
    p.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database (default: ~/.viewfinder/viewfinder.db)",
    )
    p.add_argument(
        "--cost-report",
        action="store_true",
        help="Show cumulative token usage and cost report, then exit",
    )
    p.add_argument(
        "--list-videos",
        action="store_true",
        help="List all cached videos in the database, then exit",
    )
    p.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search transcripts for a query string, then exit",
    )
    p.add_argument(
        "--export",
        type=str,
        default=None,
        help="Export a cached video as Markdown (by video ID), then exit",
    )

    # Server
    p.add_argument(
        "--serve",
        action="store_true",
        help="Start the web UI server (FastAPI + built-in frontend)",
    )
    p.add_argument("--host", default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")

    return p


def process_video(video_input: str, args: argparse.Namespace, store=None) -> str:
    """Process a single video. Returns formatted output string."""
    video_id = extract_video_id(video_input)
    verbose = not args.quiet
    target_lang = args.translate_to or args.lang

    if verbose:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"Processing: {video_id}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)

    # Check cache first
    transcript = None
    if store and not args.no_cache:
        transcript = store.get_transcript(video_id, language=target_lang)
        if transcript and verbose:
            words = transcript.word_count
            print(f"  [cache] Found cached transcript ({words:,} words)", file=sys.stderr)

    # Fetch if not cached
    if transcript is None:
        transcript = fetch_transcript(
            video_id,
            lang=args.lang,
            translate_to=args.translate_to,
            enrich=not args.no_enrich,
            whisper=not args.no_whisper,
            whisper_model=args.whisper_model,
            whisper_backend="groq" if args.fast else "local",
            correct=not args.no_correct,
            verbose=verbose,
        )
        # Save to cache
        if store:
            store.save_transcript(transcript)

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
        if store:
            store.save_screenshots(screenshot_result)

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
        backend=args.backend,
        base_url=args.base_url,
        verbose=verbose,
    )
    if store:
        transcript_id = store.save_transcript(transcript)
        store.save_summary(summary, transcript_id)

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


def _format_cost_report(store) -> str:
    """Format a cost report from the storage layer."""
    summary = store.get_cost_summary()
    by_model = store.get_cost_by_model()

    lines = [
        "Viewfinder Cost Report",
        "=" * 40,
        f"Total summaries:  {summary['total_summaries']}",
        f"Total tokens:     {summary['total_tokens']:,}",
        f"  Input tokens:   {summary['total_input_tokens']:,}",
        f"  Output tokens:  {summary['total_output_tokens']:,}",
    ]

    if by_model:
        lines.extend(["", "By model:"])
        for row in by_model:
            total = row["input_tokens"] + row["output_tokens"]
            lines.append(f"  {row['model']}: {row['count']} runs, {total:,} tokens")

    lines.extend(["", f"Videos in DB:     {store.video_count()}"])
    return "\n".join(lines)


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Initialize storage
    from .storage import Storage

    store = Storage(db_path=args.db)

    # Handle --serve
    if args.serve:
        import uvicorn

        store.close()
        print(f"Starting Viewfinder web UI on http://{args.host}:{args.port}", file=sys.stderr)
        uvicorn.run("viewfinder.server:app", host=args.host, port=args.port, reload=False)
        sys.exit(0)

    # Handle --cost-report
    if args.cost_report:
        print(_format_cost_report(store))
        store.close()
        sys.exit(0)

    # Handle --list-videos
    if args.list_videos:
        videos_list = store.list_videos()
        if not videos_list:
            print("No videos in database.")
        else:
            print(f"{'VIDEO ID':<15} {'TITLE':<40} {'TRANSCRIPTS':>5} {'SUMMARIES':>5}")
            print("-" * 70)
            for v in videos_list:
                title = (v["title"] or "Unknown")[:38]
                print(
                    f"{v['video_id']:<15} {title:<40} "
                    f"{v['transcript_count']:>5} {v['summary_count']:>5}"
                )
        store.close()
        sys.exit(0)

    # Handle --search
    if args.search:
        results = store.search_transcripts(args.search)
        if not results:
            print(f"No results for: {args.search}")
        else:
            print(f"Found {len(results)} result(s) for: {args.search}\n")
            for r in results:
                title = r.get("title") or r["video_id"]
                print(f"  {r['video_id']}  {title}")
                print(f"    ...{r['snippet']}...")
                print()
        store.close()
        sys.exit(0)

    # Handle --export
    if args.export:
        from .formatters import to_ingest_markdown
        from .models import IngestResult, SummaryResult

        vid = args.export
        transcript = store.get_transcript(vid)
        if transcript is None:
            print(f"Error: No transcript found for {vid}", file=sys.stderr)
            store.close()
            sys.exit(1)
        summaries = store.get_summaries(vid)
        summary_obj = None
        if summaries:
            s = summaries[0]
            summary_obj = SummaryResult(
                transcript=transcript,
                summary=s["summary"],
                model=s["model"],
                prompt_template=s["prompt_template"],
                input_tokens=s.get("input_tokens"),
                output_tokens=s.get("output_tokens"),
                generated_at=s.get("generated_at", ""),
            )
        ingest = IngestResult(transcript=transcript, summary=summary_obj)
        print(to_ingest_markdown(ingest))
        store.close()
        sys.exit(0)

    # Handle --list-languages
    if args.list_languages:
        if not args.video:
            print("Error: --list-languages requires a video URL or ID", file=sys.stderr)
            store.close()
            sys.exit(1)
        from .transcript import list_available_languages

        video_id = extract_video_id(args.video)
        languages = list_available_languages(video_id)
        print(f"Available transcripts for {video_id}:")
        for lang in languages:
            gen_tag = " (auto-generated)" if lang["is_generated"] else ""
            trans_tag = " [translatable]" if lang["translatable"] else ""
            print(f"  {lang['code']:>5}  {lang['name']}{gen_tag}{trans_tag}")
        store.close()
        sys.exit(0)

    has_input = args.video or args.batch or args.playlist or args.channel or args.feed
    if not has_input:
        store.close()
        parser.print_help()
        sys.exit(1)

    if args.screenshots and not args.output_dir:
        print(
            "Warning: --screenshots without --output-dir; "
            "screenshots will be saved to ./screenshots/",
            file=sys.stderr,
        )

    # Collect video inputs from all sources
    videos: list[str] = []
    log = (lambda msg: print(msg, file=sys.stderr)) if not args.quiet else (lambda _: None)

    if args.playlist:
        from .ingest import extract_playlist_video_ids

        ids = extract_playlist_video_ids(args.playlist, verbose=not args.quiet)
        videos.extend(ids)
        log(f"Playlist: {len(ids)} videos queued")

    if args.channel:
        from .ingest import extract_channel_video_ids

        ids = extract_channel_video_ids(
            args.channel, limit=args.channel_limit, verbose=not args.quiet
        )
        videos.extend(ids)
        log(f"Channel: {len(ids)} videos queued")

    if args.feed:
        from .ingest import fetch_feed_video_ids

        ids = fetch_feed_video_ids(args.feed, verbose=not args.quiet)
        videos.extend(ids)
        log(f"Feed: {len(ids)} videos queued")

    if args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            print(f"Error: Batch file not found: {args.batch}", file=sys.stderr)
            store.close()
            sys.exit(1)
        batch_ids = [
            line.strip()
            for line in batch_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        videos.extend(batch_ids)
        log(f"Batch file: {len(batch_ids)} videos queued")

    if args.video:
        videos.append(args.video)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_videos: list[str] = []
    for v in videos:
        if v not in seen:
            seen.add(v)
            unique_videos.append(v)
    videos = unique_videos

    if not videos:
        print("No videos to process.", file=sys.stderr)
        store.close()
        sys.exit(0)

    log(f"Processing {len(videos)} video(s)...")

    ext_map = {"json": "json", "md": "md", "text": "txt"}
    ext = ext_map[args.output_format]

    # Rate limiter for bulk modes
    from .ingest import RateLimiter

    limiter = RateLimiter(delay=args.rate_limit) if len(videos) > 1 else None

    for i, video_input in enumerate(videos):
        try:
            output = process_video(video_input, args, store=store)

            if args.output_dir:
                vid = extract_video_id(video_input)
                save_output(output, vid, args.output_dir, ext)
            else:
                print(output)

            # Webhook notification
            if args.webhook_url and not args.transcript_only:
                from .ingest import send_webhook

                vid = extract_video_id(video_input)
                send_webhook(
                    args.webhook_url,
                    {"event": "summary_created", "video_id": vid},
                    verbose=not args.quiet,
                )

            if limiter:
                limiter.on_success()
                if i < len(videos) - 1:
                    limiter.wait()

        except Exception as e:
            print(f"\nError processing {video_input}: {e}", file=sys.stderr)
            if limiter and limiter.should_retry:
                wait = limiter.on_failure()
                log(f"  [retry] Backing off {wait:.1f}s...")
                time.sleep(wait)
            elif len(videos) == 1:
                store.close()
                sys.exit(1)

    if not args.quiet:
        print(f"\nDone. Processed {len(videos)} video(s).", file=sys.stderr)

    store.close()


if __name__ == "__main__":
    main()
