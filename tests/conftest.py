"""Shared test configuration and fixtures."""

import pytest


def _is_youtube_rate_limit(exc: BaseException) -> bool:
    """Check if an exception is a YouTube rate limit / IP block."""
    name = type(exc).__name__
    if name in ("IpBlocked", "RequestBlocked"):
        return True
    msg = str(exc)
    return "429" in msg or "IpBlocked" in msg or "too many requests" in msg.lower()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Auto-skip network tests that fail due to YouTube rate limiting."""
    try:
        result = yield
    except BaseException as exc:
        is_network = any(mark.name == "network" for mark in item.iter_markers())
        if is_network and _is_youtube_rate_limit(exc):
            pytest.skip(f"YouTube rate limited: {type(exc).__name__}")
        raise
    return result
