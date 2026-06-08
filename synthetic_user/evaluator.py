"""Evaluator (architecture2.md section 2.5). Walking-skeleton stubs.
Real: 3-layer hybrid (rules -> multi-hat panel Layer 2 -> classifier). SOLE memory writer."""
from __future__ import annotations
from synthetic_user.types import Cycle, Score
from synthetic_user.reports import DecisionReport, ReportBuffer
from synthetic_user.memory import Memory


def evaluate(cycle: Cycle, criteria: list[str], buffer: ReportBuffer) -> Score:
    """Layer 1 stub: a present, non-empty deliverable passes. Real rules + Layer 2 later."""
    has_deliverable = cycle.deliverable is not None and bool(cycle.deliverable.content)
    score = Score(
        value=0.9 if has_deliverable else 0.0,
        passed=has_deliverable,
        criteria_met={c: has_deliverable for c in (criteria or ["deliverable exists"])},
    )
    buffer.add(DecisionReport(
        component="evaluator", decision_type="reliability_eval",
        selected="pass" if score.passed else "fail",
        rationale="stub layer-1: deliverable present",
        confidence="high", self_reported=True,
        component_specific={"score": score.value},
    ))
    return score


def ingest_reports(buffer: ReportBuffer, memory: Memory) -> int:
    """Evaluator-mediated write (section 2.6/2.8): drain buffer -> validate -> persist."""
    return memory.write_reports(buffer.drain())
