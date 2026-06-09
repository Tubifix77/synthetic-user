"""Brain dispatch stub (architecture2.md section 2.9 — steering brain).

Real: triple-check lock + The Prompt invocation at Layer 6 for hard cases.
Stub (scenarios 3–4): returns a sensible generic answer so the test can verify
the reactive and proactive paths without a full brain implementation.
The answer is intentionally generic — it tells CC to proceed with reasonable
defaults rather than genuinely reasoning about the question.
"""
from __future__ import annotations


_GENERIC_ANSWER = (
    "The synthetic-user director answers: proceed with reasonable defaults. "
    "Use a general-purpose implementation. Make your own judgment on any "
    "ambiguous parameters — do not ask for further clarification."
)


def answer(question: str) -> str:
    """Return the brain's verdict for a question CC raised."""
    return _GENERIC_ANSWER
