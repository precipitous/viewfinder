"""AI summarization via Claude (or compatible LLM backends)."""

import sys
import textwrap

from .models import SummaryResult, TranscriptResult

# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

PROMPTS: dict[str, str] = {
    "default": textwrap.dedent("""\
        You are an expert content analyst. Summarize the following YouTube video transcript.

        **Video**: {title}
        **Channel**: {channel}
        **Duration**: {duration}

        Provide:
        1. A concise TL;DR (2-3 sentences)
        2. Key points and takeaways (bullet points)
        3. Notable quotes or claims worth verifying
        4. Topics covered (for tagging/categorization)

        Transcript:
        {transcript}
    """),
    "brief": textwrap.dedent("""\
        Summarize this YouTube video transcript in 3-5 sentences.
        Focus on the core argument or message.

        **Video**: {title}

        Transcript:
        {transcript}
    """),
    "detailed": textwrap.dedent("""\
        You are an expert content analyst. Provide a comprehensive analysis
        of this YouTube video transcript.

        **Video**: {title}
        **Channel**: {channel}
        **Duration**: {duration}

        Provide:
        1. Executive summary (1 paragraph)
        2. Detailed section-by-section breakdown with timestamps
        3. Key arguments and supporting evidence presented
        4. Claims that warrant fact-checking or further research
        5. Target audience and content quality assessment
        6. Related topics for further exploration
        7. Topics/tags for categorization

        Transcript:
        {transcript}
    """),
    "technical": textwrap.dedent("""\
        You are a technical analyst. Extract structured knowledge from
        this YouTube video transcript.

        **Video**: {title}
        **Channel**: {channel}

        Provide:
        1. Technical concepts explained (with definitions)
        2. Tools, frameworks, or technologies mentioned
        3. Code snippets or technical procedures described
        4. Architecture or design decisions discussed
        5. Best practices or anti-patterns mentioned
        6. Prerequisites or assumed knowledge

        Transcript:
        {transcript}
    """),
}


def list_prompts() -> list[str]:
    """Return available prompt template names."""
    return list(PROMPTS.keys())


# ---------------------------------------------------------------------------
# Duration Formatting
# ---------------------------------------------------------------------------


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "Unknown"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------


def summarize(
    transcript: TranscriptResult,
    prompt_key: str = "default",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    api_key: str | None = None,
    verbose: bool = True,
) -> SummaryResult:
    """Summarize a transcript using Claude.

    Args:
        transcript: The transcript to summarize.
        prompt_key: Key into PROMPTS dict. Use list_prompts() to see options.
        model: Anthropic model identifier.
        max_tokens: Max output tokens.
        api_key: Anthropic API key; falls back to ANTHROPIC_API_KEY env var.
        verbose: Print progress to stderr.
    """
    import anthropic

    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)
    client = anthropic.Anthropic(api_key=api_key)

    template = PROMPTS.get(prompt_key, PROMPTS["default"])

    # Truncate if extremely long (~75k tokens is safe for Claude)
    full_text = transcript.full_text
    max_chars = 300_000
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "\n\n[...transcript truncated...]"

    prompt = template.format(
        title=transcript.meta.title or "Unknown",
        channel=transcript.meta.channel or "Unknown",
        duration=format_duration(transcript.meta.duration_seconds),
        transcript=full_text,
    )

    log(f"  [llm] Sending {len(full_text):,} chars to {model}...")

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    summary_text = "\n".join(block.text for block in response.content if hasattr(block, "text"))

    result = SummaryResult(
        transcript=transcript,
        summary=summary_text,
        model=model,
        prompt_template=prompt_key,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    log(f"  [done] Summary generated ({result.output_tokens} output tokens)")
    return result
