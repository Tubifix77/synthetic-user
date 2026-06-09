"""Scenario 6 (Triage rejection) - architecture2.md section 10.3.

Malformed/too-vague request enters. Triage Stage 1 rules don't match (goal is
non-empty but underspecified). Stage 2 Haiku classifies as reject-with-clarification.
No cycle ever starts. Run carries a structured rejection reason.

Verifies: triage rejection path, Stage 2 LLM escalation, structured rejection
format, no cycle started on rejected request.

INTEGRATION TEST — invokes a real `claude -p` subprocess for Stage 2 classification.
Run with: pytest -m integration
"""
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, Route

pytestmark = pytest.mark.integration


def test_scenario_06_triage_rejects_vague_request():
    mem = Memory()
    run = Orchestrator(memory=mem).run(Request(
        goal="write me something interesting"  # passes Stage 1 (non-empty) but too vague for Stage 2
    ))

    # Triage must have rejected — no cycles should have started.
    assert run.route is Route.REJECT
    assert len(run.cycles) == 0

    # A structured rejection reason must be present.
    assert run.rejected_reason is not None
    assert len(run.rejected_reason) > 10  # not an empty string

    # No deliverable (nothing was executed).
    assert run.deliverable is None

    # Triage report must exist in memory with route=reject and stage_reached >= 2.
    triage_reports = [r for r in mem.all_reports() if r.component == "triage"]
    assert len(triage_reports) >= 1
    triage = triage_reports[0]
    assert triage.selected == "reject"
    assert triage.component_specific.get("stage_reached", 1) >= 2


def test_scenario_06_triage_accepts_loop_worthy_request():
    """Stage 1 must not over-reject: a clear actionable goal enters the loop."""
    mem = Memory()
    run = Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    assert run.route is Route.LOOP
    assert len(run.cycles) >= 1
