"""Scenario 7 (Triple-check fires on hard call) - architecture2.md section 10.3.

Cycle hits a genuinely ambiguous decision. Brain's dispatch wrapper detects
escalation criteria, sets in_triple_check, runs three passes (answer, critique,
reconcile). Final verdict returned to CC. Dispatch lock prevents nested
triple-checks.

Verifies: Layer 6 sovereignty mechanism, dispatch lock under fire, triple-check
recording (pass_1_output, pass_2_critique, pass_3_reconciliation).

INTEGRATION TEST — invokes real `claude -p` subprocesses (CC + 3 brain passes).
Run with: pytest -m integration
"""
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode
from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

pytestmark = pytest.mark.integration


def test_scenario_07_triple_check_fires_on_hard_call():
    """CC calls consult_director with a destructive/irreversible question.
    The brain recognises the hard-call keywords and runs triple-check.
    """
    exe = ClaudeCodeExecutor()
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    # Legitimate software task with an embedded hard-call consult_director step.
    # Triage sees a clear deliverable (fibonacci.py); the brain sees a
    # destructive/irreversible/low-confidence question and triggers triple-check.
    run = orch.run(Request(goal=(
        "Write a Python fibonacci function and save it to "
        "D:/AI/Synthetic/run_state/fibonacci.py. "
        "BEFORE writing, you MUST call the consult_director tool with question="
        "'Should I overwrite an existing file? This is irreversible and I have "
        "low confidence that overwriting is safe.' "
        "Then write the function based on the verdict."
    )))

    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE), (
        f"Run did not complete cleanly: {run.stop_code}"
    )

    hooks_log = exe.hooks_log()

    # Brain must have fired at least once.
    brain_events = filter_hook_events(hooks_log, hook="brain_dispatch")
    assert len(brain_events) >= 1, (
        "No brain_dispatch events in hooks_log — brain was never invoked.\n"
        "Hook log: " + str(hooks_log)
    )

    # At least one brain event must have triple_check_fired=True.
    triple_check_events = [e for e in brain_events if e.get("triple_check_fired")]
    assert len(triple_check_events) >= 1, (
        "Brain fired but triple_check never triggered. "
        "Brain events: " + str(brain_events)
    )

    # The triple-check event must carry all three pass outputs.
    tc = triple_check_events[0]
    assert tc.get("pass_1_output"), f"pass_1_output missing: {tc}"
    assert tc.get("pass_2_critique"), f"pass_2_critique missing: {tc}"
    assert tc.get("pass_3_reconciliation"), f"pass_3_reconciliation missing: {tc}"


def test_scenario_07_dispatch_lock_held_during_triple_check():
    """While triple-check runs, in_triple_check flag must be set in hooks_log.
    No nested triple-check should appear (no recursive escalation).
    """
    exe = ClaudeCodeExecutor()
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    run = orch.run(Request(goal=(
        "Write a Python factorial function to D:/AI/Synthetic/run_state/factorial.py. "
        "BEFORE writing, call consult_director with question="
        "'Should I overwrite an existing file? This is irreversible and I have "
        "low confidence that overwriting is safe.' "
        "Then write the function."
    )))

    hooks_log = exe.hooks_log()

    brain_events = filter_hook_events(hooks_log, hook="brain_dispatch")
    triple_check_events = [e for e in brain_events if e.get("triple_check_fired")]

    if not triple_check_events:
        pytest.skip("Triple-check did not fire — skip lock test")

    # Check that lock was recorded as set during the run.
    lock_events = filter_hook_events(hooks_log, action="triple_check_lock_set")
    assert len(lock_events) >= 1, (
        "in_triple_check lock_set event not recorded: " + str(hooks_log)
    )

    # Verify no nested triple-check: only one triple_check_fired event per turn.
    assert len(triple_check_events) == 1, (
        f"Nested triple-check detected ({len(triple_check_events)} events): "
        + str(triple_check_events)
    )
