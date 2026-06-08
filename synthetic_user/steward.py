"""Context steward (architecture2.md section 2.7). Placeholder for the walking
skeleton (not exercised by scenario 1; real monitor is hook-based, scenarios 5/11)."""
from __future__ import annotations


class Steward:
    def __init__(self) -> None:
        self.counted_tokens = 0

    def note(self, tokens: int) -> None:
        self.counted_tokens += tokens
