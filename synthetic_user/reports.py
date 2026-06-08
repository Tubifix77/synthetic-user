"""Decision Reports (architecture2.md section 2.8). Walking-skeleton: in-memory
schema + buffer. Reports route THROUGH the evaluator to memory (section 2.6 rule)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass
class DecisionReport:
    component: str                       # triage | seeder | director | steward | evaluator
    decision_type: str
    selected: str = ""
    rationale: str = ""
    confidence: str = "medium"           # low | medium | high
    reversibility: str = "high"          # low | medium | high
    audit_flags: list[str] = field(default_factory=list)
    self_reported: bool = False
    report_minimal: bool = False
    component_specific: dict[str, Any] = field(default_factory=dict)
    report_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str | None = None
    cycle_id: int | None = None


class ReportBuffer:
    """Per-Run in-memory queue. Components append; the evaluator drains at cycle close."""
    def __init__(self) -> None:
        self._items: list[DecisionReport] = []

    def add(self, report: DecisionReport) -> None:
        self._items.append(report)

    def drain(self) -> list[DecisionReport]:
        items, self._items = self._items, []
        return items

    def __len__(self) -> int:
        return len(self._items)
