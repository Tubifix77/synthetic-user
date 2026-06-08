"""Memory (architecture2.md section 2.6). Walking-skeleton: in-memory.
Real v1 = SQLite (episodic/strategy/failure) + vector store. SINGLE WRITER = evaluator."""
from __future__ import annotations
from synthetic_user.reports import DecisionReport


class Memory:
    def __init__(self) -> None:
        self._reports: list[DecisionReport] = []

    # Only the evaluator should call this (section 2.6 write-gating).
    def write_reports(self, reports: list[DecisionReport]) -> int:
        self._reports.extend(reports)
        return len(reports)

    def all_reports(self) -> list[DecisionReport]:
        return list(self._reports)
