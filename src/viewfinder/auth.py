"""API key authentication and rate limiting middleware for Viewfinder."""

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_KEY_SECURITY = Security(API_KEY_HEADER)
_REQUIRE_API_KEY = None  # set after function definition


async def require_api_key(
    request: Request,
    api_key: str | None = _API_KEY_SECURITY,
) -> dict:
    """Validate API key and enforce rate limits.

    Returns the API key record dict. Raises 401/429 on failure.

    If no API keys exist in the database, auth is disabled (open access).
    """
    from .server import get_store

    store = get_store()

    # If no API keys exist, auth is disabled
    keys = store.list_api_keys()
    if not keys:
        return {"key": None, "name": "anonymous", "is_admin": 1, "rate_limit_rpm": 0}

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    record = store.get_api_key(api_key)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Rate limiting
    if record["rate_limit_rpm"] > 0:
        count = store.get_request_count_last_minute(api_key)
        if count >= record["rate_limit_rpm"]:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({record['rate_limit_rpm']} requests/minute)",
            )

    return record


_REQUIRE_API_KEY = Security(require_api_key)


async def require_admin(
    key_record: dict = _REQUIRE_API_KEY,
) -> dict:
    """Require admin-level API key."""
    if not key_record.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return key_record
