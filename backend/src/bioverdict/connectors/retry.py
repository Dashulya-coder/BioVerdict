"""Retry policy for connector HTTP calls.

Retry only what can succeed on a second try: network failures, HTTP 429 and 5xx.
A 4xx such as 404 is a bad request, so repeating it only wastes time.
"""

from __future__ import annotations

import httpx
from tenacity import RetryCallState, wait_exponential

MAX_ATTEMPTS = 3
# Three attempts wait at most twice, so a run is held up by 2 x 10 s here; the agent budget is 90 s.
MAX_RETRY_AFTER_S = 10.0

_exponential = wait_exponential(multiplier=0.5, max=8)


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


def retry_after_seconds(exc: BaseException) -> float | None:
    """Seconds requested by a `Retry-After` header (integer form only), capped."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    value = exc.response.headers.get("Retry-After")
    if value is None or not value.isdigit():
        return None
    return min(float(value), MAX_RETRY_AFTER_S)


def wait_for_retry(state: RetryCallState) -> float:
    """Honour Retry-After when the server sent one, otherwise back off exponentially."""
    exc = state.outcome.exception() if state.outcome else None
    requested = retry_after_seconds(exc) if exc else None
    return requested if requested is not None else _exponential(state)
