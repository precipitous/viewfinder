"""Output formatters for Viewfinder results."""

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum

from .models import IngestResult, ScreenshotResult, SummaryResult, TranscriptResult
from .summarize import format_duration


def _json_default(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def to_json(
    result: SummaryResult | TranscriptResult | ScreenshotResult | IngestResult,
    pretty: bool = True,
) -> str:
    """Serialize result to JSON."""
    data = result.to_dict() if hasattr(result, "to_dict") else asdict(result)
    return json.dumps(data, indent=2 if pretty else None, default=_json_default)


def to_markdown(result: SummaryResult) -> str:
    """Format summary as markdown."""
    meta = result.transcript.meta
    lines = [
        f"# {meta.title or 'YouTube Video Summary'}",
        "",
        f"**Channel:** {meta.channel or 'Unknown'}  ",
        f"**Duration:** {format_duration(meta.duration_seconds)}  ",
        f"**URL:** {meta.url}  ",
        f"**Transcript source:** {result.transcript.source.value}  ",
        f"**Language:** {result.transcript.language}  ",
    ]
    if result.transcript.translated_from:
        lines.append(f"**Translated from:** {result.transcript.translated_from}  ")
    lines.extend(
        [
            f"**Words:** {result.transcript.word_count:,}  ",
            f"**Model:** {result.model}  ",
            f"**Prompt:** {result.prompt_template}  ",
            f"**Generated:** {result.generated_at}  ",
            "",
            "---",
            "",
            result.summary,
        ]
    )
    if result.input_tokens:
        lines.extend(
            [
                "",
                "---",
                f"*Tokens: {result.input_tokens:,} in / {result.output_tokens:,} out*",
            ]
        )
    return "\n".join(lines)


def to_transcript_text(result: TranscriptResult, timestamps: bool = False) -> str:
    """Output raw transcript text, optionally with timestamps."""
    header_parts = []
    if result.translated_from:
        header_parts.append(f"[Translated from {result.translated_from} to {result.language}]")

    if not timestamps:
        if header_parts:
            return "\n".join(header_parts) + "\n\n" + result.full_text
        return result.full_text

    lines = list(header_parts)
    if header_parts:
        lines.append("")
    for s in result.snippets:
        m, sec = divmod(int(s.start), 60)
        h, m = divmod(m, 60)
        ts = f"[{h:02d}:{m:02d}:{sec:02d}]"
        lines.append(f"{ts} {s.text}")
    return "\n".join(lines)


def to_screenshot_text(result: ScreenshotResult) -> str:
    """Format screenshot result as text."""
    meta = result.meta
    lines = [
        f"Screenshots for: {meta.title or meta.video_id}",
        f"Interval: every {result.interval_seconds}s",
        f"Count: {len(result.screenshots)}",
        f"Directory: {result.output_dir}",
        "",
    ]
    for s in result.screenshots:
        lines.append(f"  [{s.timestamp_str}] {s.path}")
    return "\n".join(lines)


def to_ingest_markdown(result: IngestResult) -> str:
    """Format a full ingest result (transcript + screenshots) as markdown."""
    meta = result.transcript.meta
    lines = [
        f"# {meta.title or 'YouTube Video'}",
        "",
        f"**Channel:** {meta.channel or 'Unknown'}  ",
        f"**Duration:** {format_duration(meta.duration_seconds)}  ",
        f"**URL:** {meta.url}  ",
        f"**Language:** {result.transcript.language}  ",
    ]
    if result.transcript.translated_from:
        lines.append(f"**Translated from:** {result.transcript.translated_from}  ")
    lines.extend(
        [
            f"**Words:** {result.transcript.word_count:,}  ",
            "",
        ]
    )

    if result.screenshots and result.screenshots.screenshots:
        lines.extend(
            [
                "## Screenshots",
                "",
                f"*{len(result.screenshots.screenshots)} frames "
                f"every {result.screenshots.interval_seconds}s*",
                "",
            ]
        )
        for s in result.screenshots.screenshots:
            lines.append(f"- `[{s.timestamp_str}]` {s.path}")
        lines.append("")

    lines.extend(
        [
            "## Transcript",
            "",
            result.transcript.full_text,
        ]
    )

    if result.summary:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Summary",
                "",
                result.summary.summary,
            ]
        )

    return "\n".join(lines)
