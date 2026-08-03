"""Retry helpers for transient LLM errors.

Bedrock's ConverseStream API regularly returns short-lived `internalServerException`
or `ThrottlingException` errors mid-stream. Without retries those bubble up and
kill the entire LangGraph run. We wrap every `model.invoke(...)` in nodes with
`call_with_retry`, which backs off exponentially on a curated set of transient
errors and re-raises everything else immediately.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY = 1.5
DEFAULT_MAX_DELAY = 12.0

_RETRYABLE_EXCEPTION_NAMES: frozenset[str] = frozenset(
    {
        # botocore / boto3
        "EventStreamError",
        "ThrottlingException",
        "ModelStreamErrorException",
        "ModelTimeoutException",
        "ModelErrorException",
        "ServiceUnavailableException",
        "InternalServerException",
        # httpx / urllib3 transient
        "ReadTimeout",
        "ConnectTimeout",
        "RemoteProtocolError",
        "ProtocolError",
        "ReadError",
        "ConnectError",
    }
)

_RETRYABLE_TOKENS: tuple[str, ...] = (
    "internalServerException",
    "InternalServerException",
    "ServiceUnavailable",
    "Throttl",
    "throttl",
    "timed out",
    "Read timed out",
    "internal server error",
    "Bedrock is unable to process",
    "TooManyRequests",
    "RequestTimeout",
)


def _is_retryable(exc: BaseException) -> bool:
    if type(exc).__name__ in _RETRYABLE_EXCEPTION_NAMES:
        return True
    msg = str(exc)
    return any(tok in msg for tok in _RETRYABLE_TOKENS)


def call_with_retry(
    fn: Callable[..., T],
    *args: Any,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    label: str = "llm",
    **kwargs: Any,
) -> T:
    """Call `fn(*args, **kwargs)`, retrying on transient Bedrock/network errors.

    Uses exponential backoff with jitter. Non-retryable errors are re-raised
    immediately so structural bugs surface fast.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if attempt >= max_attempts or not _is_retryable(exc):
                raise
            last_exc = exc
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.3)
            logger.warning(
                "[%s] attempt %d/%d failed (%s: %s); retrying in %.1fs",
                label,
                attempt,
                max_attempts,
                type(exc).__name__,
                exc,
                delay,
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


__all__ = ["call_with_retry"]
