"""Seeder (architecture2.md section 2.1). Walking-skeleton stubs.
Real: multi-lens reflection + selection-over-generation grounding (v1.4) + cycle prep."""
from __future__ import annotations
from synthetic_user.types import Cycle, Run, SeederDecision, StopCode
from synthetic_user.reports import DecisionReport, ReportBuffer

# v1.3: at cycle 0 the wrapper asks CC to declare done-when criteria. Stubbed here.
CRITERIA_DECLARATION_PROMPT = (
    "Before starting, list the concrete conditions that would make this task complete."
)


def cold_start(goal: str, buffer: ReportBuffer) -> str:
    """Cycle 0: pass-through (section 2.1)."""
    buffer.add(DecisionReport(
        component="seeder", decision_type="cold_start",
        selected="passthrough", rationale="cold start: no prior cycle to reflect on",
    ))
    return goal


def reflect(cycle: Cycle, run: Run, buffer: ReportBuffer) -> SeederDecision:
    """Cycle-boundary reflection. STUB: if the cycle passed, converge to COMPLETE.
    Real version runs the multi-lens panel and may instead return a direction."""
    if cycle.score is not None and cycle.score.passed:
        decision = SeederDecision(stop=StopCode.COMPLETE)
        rationale = "stub: cycle passed; all lenses converge on done"
    else:
        decision = SeederDecision(direction="retry/improve", criteria=["address failures"])
        rationale = "stub: cycle did not pass; continue"
    buffer.add(DecisionReport(
        component="seeder", decision_type="reflect",
        selected=(decision.stop.value if decision.stop else "continue"),
        rationale=rationale,
        component_specific={"refinement_depth": cycle.index},
    ))
    return decision
