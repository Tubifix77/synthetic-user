"""General-purpose utilities for the synthetic-user control system."""
from __future__ import annotations

import json
import re
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

# Error substrings that indicate a transient rate-limit from claude -p.
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "rate_limit",
    "overloaded",
    "529",
    "too many requests",
    "429",
)


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception looks like a transient Claude rate-limit."""
    msg = str(exc).lower()
    return any(marker in msg for marker in _RATE_LIMIT_MARKERS)


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 5,
    base_delay: float = 10.0,
    max_delay: float = 120.0,
    backoff_factor: float = 2.0,
    jitter: float = 0.25,
    retryable: Callable[[Exception], bool] = is_rate_limit_error,
) -> T:
    """Call *fn* and retry on retryable errors with exponential back-off.

    Default policy targets Claude subscription rate-limits: up to 5 attempts,
    starting at 10 s, doubling each time (capped at 120 s), with ±25% jitter.

    Args:
        fn:             Zero-argument callable to invoke.
        max_attempts:   Total attempts before re-raising the last exception.
        base_delay:     Seconds to wait before the first retry.
        max_delay:      Maximum seconds between retries.
        backoff_factor: Multiplier applied to delay after each failure.
        jitter:         Fraction of delay to randomise (±jitter * delay).
        retryable:      Predicate; return True to retry, False to raise immediately.

    Returns:
        The return value of *fn* on success.

    Raises:
        The last exception raised by *fn* after all attempts are exhausted,
        or any exception for which *retryable* returns False.
    """
    delay = base_delay
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not retryable(exc):
                raise
            last_exc = exc
            if attempt == max_attempts:
                break
            jittered = delay * (1 + random.uniform(-jitter, jitter))
            time.sleep(max(0.0, jittered))
            delay = min(delay * backoff_factor, max_delay)

    raise last_exc  # type: ignore[misc]


# Matches ```json ... ``` or ``` ... ``` fenced blocks, then bare JSON as fallback.
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def extract_json_block(text: str) -> Any:
    """Extract and parse the first JSON value from *text*.

    Handles three common LLM output shapes:
    1. A fenced code block: ```json { ... } ```
    2. A bare fenced block:  ``` { ... } ```
    3. Raw JSON with no fencing (entire string is valid JSON).

    Returns the parsed Python object.

    Raises:
        ValueError: if no parseable JSON can be found in *text*.
    """
    for match in _FENCED_JSON_RE.finditer(text):
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Fallback: try the whole string (some models skip fencing).
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    raise ValueError(f"No parseable JSON found in text (first 120 chars): {text[:120]!r}")


def weighted_mean_score(
    scores: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """Return a weighted mean of evaluator hat scores, clamped to [0.0, 100.0].

    Args:
        scores:  Mapping of hat name -> raw score (any numeric range accepted;
                 values are clamped individually before aggregation).
        weights: Optional mapping of hat name -> positive weight.  Hats absent
                 from *weights* receive weight 1.0.  If omitted, all hats are
                 equally weighted.

    Returns:
        Weighted mean in [0.0, 100.0].

    Raises:
        ValueError: if *scores* is empty or all weights are zero.
    """
    if not scores:
        raise ValueError("scores must not be empty")
    weights = weights or {}
    total_weight = 0.0
    weighted_sum = 0.0
    for hat, raw in scores.items():
        w = float(weights.get(hat, 1.0))
        if w < 0:
            raise ValueError(f"weight for '{hat}' must be non-negative, got {w}")
        clamped = max(0.0, min(100.0, float(raw)))
        weighted_sum += w * clamped
        total_weight += w
    if total_weight == 0.0:
        raise ValueError("sum of weights is zero — cannot compute mean")
    return weighted_sum / total_weight


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text* without an API call.

    Uses the widely-observed rule of thumb that one token ≈ 4 bytes of UTF-8
    for English prose, adjusted slightly upward for code/JSON which tends to
    tokenise more densely.  Accurate to ±15% for typical LLM prompt content;
    good enough for a compact-threshold guard (scenario 9) where a hard cutoff
    is undesirable anyway.

    Returns a non-negative integer.
    """
    if not text:
        return 0
    byte_len = len(text.encode("utf-8"))
    return max(1, round(byte_len / 3.8))


def truncate_text(text: str, max_chars: int, *, suffix: str = "…") -> str:
    """Truncate *text* to at most *max_chars* characters, breaking at a word boundary.

    Truncation happens at the last whitespace at or before *max_chars - len(suffix)*
    so the result (including *suffix*) never exceeds *max_chars*. If the text fits,
    it is returned unchanged.

    Useful for keeping prompts within safe bounds before passing them to claude -p.
    """
    if len(text) <= max_chars:
        return text
    cut = max_chars - len(suffix)
    if cut <= 0:
        return suffix[:max_chars]
    # Walk back to the last whitespace to avoid cutting mid-word.
    boundary = text.rfind(" ", 0, cut)
    if boundary <= 0:
        boundary = cut
    return text[:boundary] + suffix
