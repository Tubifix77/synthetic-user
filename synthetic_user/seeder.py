"""Seeder (architecture2.md section 2.1). Walking-skeleton stubs.
Real: multi-lens reflection + selection-over-generation grounding (v1.4) + cycle prep."""
from __future__ import annotations
from synthetic_user.types import Cycle, Run, SeederDecision, StopCode
from synthetic_user.reports import DecisionReport, ReportBuffer

# v1.3: at cycle 0 the wrapper asks CC to declare done-when criteria. Stubbed here.
CRITERIA_DECLARATION_PROMPT = (
    "Before starting, list the concrete conditions that would make this task complete."
)

# Goals that warrant a refinement cycle (stub heuristic — real: multi-lens panel).
_COMPLEX_KEYWORDS = {"build", "create", "implement", "develop"}


def _is_complex(goal: str) -> bool:
    low = goal.lower()
    return any(kw in low for kw in _COMPLEX_KEYWORDS)


def cold_start(goal: str, buffer: ReportBuffer) -> str:
    """Cycle 0: pass-through (section 2.1)."""
    buffer.add(DecisionReport(
        component="seeder", decision_type="cold_start",
        selected="passthrough", rationale="cold start: no prior cycle to reflect on",
    ))
    return goal


def reflect(cycle: Cycle, run: Run, buffer: ReportBuffer) -> SeederDecision:
    """Cycle-boundary multi-lens reflection (stub).

    Cycle 0 of a complex goal: production lens sees a working deliverable;
    skeptical lens surfaces untested edge cases — return a refinement direction.
    Cycle 1+ of a complex goal (or any simple goal that passed): stop.
    """
    passed = cycle.score is not None and cycle.score.passed
    complex_goal = _is_complex(run.request.goal)

    # Multi-lens panel (stubbed): emit one report per run of the panel.
    # Real version runs production / skeptical / adversary hats in parallel.
    if complex_goal and cycle.index == 0 and passed:
        # Skeptical lens surfaces edge cases — direct a refinement cycle.
        direction = f"add adversarial test cases and edge-case handling for: {cycle.goal}"
        criteria = ["edge cases handled", "adversarial tests pass"]
        decision = SeederDecision(direction=direction, criteria=criteria)
        lens_verdict = "refine"
        rationale = (
            "stub multi-lens: production lens=pass; skeptical lens=edge cases unhandled; "
            "adversary lens=inputs not tested — directing refinement cycle"
        )
        stop_code_str = "continue"
    elif passed:
        stop_code = StopCode.REFINEMENT_COMPLETE if complex_goal else StopCode.COMPLETE
        decision = SeederDecision(stop=stop_code)
        lens_verdict = "done"
        rationale = (
            "stub multi-lens: all lenses converge on done"
            + (" (refinement complete)" if complex_goal else "")
        )
        stop_code_str = stop_code.value
    else:
        decision = SeederDecision(direction="retry/improve", criteria=["address failures"])
        lens_verdict = "retry"
        rationale = "stub multi-lens: cycle did not pass; all lenses agree: continue"
        stop_code_str = "continue"

    buffer.add(DecisionReport(
        component="seeder", decision_type="multi_lens_reflect",
        selected=lens_verdict,
        rationale=rationale,
        component_specific={
            "refinement_depth": cycle.index,
            "complex_goal": complex_goal,
            "stop_code": stop_code_str,
        },
    ))
    return decision
