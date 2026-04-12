"""AI summarization via pluggable LLM backends.

Backends:
    - claude: Anthropic Claude API (default)
    - openai: OpenAI-compatible API (works with local Qwen R1, vLLM, ollama, etc.)
"""

import sys
import textwrap
from dataclasses import dataclass

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
# LLM Backend Interface
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Standardized response from any LLM backend."""

    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def _call_claude(
    prompt: str,
    model: str,
    max_tokens: int,
    api_key: str | None,
) -> LLMResponse:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "\n".join(block.text for block in response.content if hasattr(block, "text"))
    return LLMResponse(
        text=text,
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def _call_openai_compat(
    prompt: str,
    model: str,
    max_tokens: int,
    api_key: str | None,
    base_url: str | None = None,
) -> LLMResponse:
    """Call an OpenAI-compatible API (vLLM, ollama, Qwen R1, etc.)."""
    import httpx

    url = (base_url or "http://localhost:8000") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = httpx.post(url, json=payload, headers=headers, timeout=300)
    resp.raise_for_status()
    data = resp.json()

    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return LLMResponse(
        text=text,
        model=model,
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
    )


# Backend registry
BACKENDS = {
    "claude": _call_claude,
    "openai": _call_openai_compat,
}


def list_backends() -> list[str]:
    """Return available backend names."""
    return list(BACKENDS.keys())


# ---------------------------------------------------------------------------
# Summarization (public API)
# ---------------------------------------------------------------------------


def _build_prompt(transcript: TranscriptResult, prompt_key: str) -> str:
    """Build the LLM prompt from a template and transcript."""
    template = PROMPTS.get(prompt_key, PROMPTS["default"])
    full_text = transcript.full_text
    max_chars = 300_000
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "\n\n[...transcript truncated...]"
    return template.format(
        title=transcript.meta.title or "Unknown",
        channel=transcript.meta.channel or "Unknown",
        duration=format_duration(transcript.meta.duration_seconds),
        transcript=full_text,
    )


def summarize(
    transcript: TranscriptResult,
    prompt_key: str = "default",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    api_key: str | None = None,
    backend: str = "claude",
    base_url: str | None = None,
    verbose: bool = True,
) -> SummaryResult:
    """Summarize a transcript using a pluggable LLM backend.

    Args:
        transcript: The transcript to summarize.
        prompt_key: Key into PROMPTS dict. Use list_prompts() to see options.
        model: Model identifier (meaning depends on backend).
        max_tokens: Max output tokens.
        api_key: API key for the backend.
        backend: LLM backend to use ("claude" or "openai").
        base_url: Base URL for OpenAI-compatible backends.
        verbose: Print progress to stderr.
    """
    log = (lambda msg: print(msg, file=sys.stderr)) if verbose else (lambda _: None)

    prompt = _build_prompt(transcript, prompt_key)
    log(f"  [llm] Sending {len(transcript.full_text):,} chars to {model} via {backend}...")

    if backend == "openai":
        response = _call_openai_compat(prompt, model, max_tokens, api_key, base_url)
    else:
        response = _call_claude(prompt, model, max_tokens, api_key)

    result = SummaryResult(
        transcript=transcript,
        summary=response.text,
        model=response.model,
        prompt_template=prompt_key,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )

    tokens_msg = f"{result.output_tokens} output tokens" if result.output_tokens else "done"
    log(f"  [done] Summary generated ({tokens_msg})")
    return result
