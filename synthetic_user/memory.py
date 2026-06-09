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

    def query_reports(
        self,
        *,
        component: str | None = None,
        decision_type: str | None = None,
        has_flag: str | None = None,
    ) -> list[DecisionReport]:
        """Filter the report store. All supplied criteria are ANDed.

        Args:
            component:     match reports where report.component == value
            decision_type: match reports where report.decision_type == value
            has_flag:      match reports where value is in report.audit_flags
        """
        results = self._reports
        if component is not None:
            results = [r for r in results if r.component == component]
        if decision_type is not None:
            results = [r for r in results if r.decision_type == decision_type]
        if has_flag is not None:
            results = [r for r in results if has_flag in r.audit_flags]
        return list(results)
