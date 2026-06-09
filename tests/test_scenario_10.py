"""Scenario 10 (Dispatch lock prevents double-fire) - architecture2.md section 10.3.

Construct a Run where both the proactive (consult_director) and reactive (Stop-hook)
paths could fire on the same logical halt — CC calls consult_director but also emits
halt-language at turn end. The dispatch lock (set when consult_director fires)
must prevent the Stop hook from dispatching the brain a second time on the same turn.

Verifies: FM-10 mitigation, shared lock state between consult_director and Stop-hook
router, no double-firing.

INTEGRATION TEST — invokes a real `claude -p` subprocess.
Run with: pytest -m integration
"""
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode
from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

pytestmark = pytest.mark.integration


def test_scenario_10_dispatch_lock_prevents_double_fire():
    # Standard executor — SessionStart injects consult_director instruction.
    exe = ClaudeCodeExecutor()
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    # Prompt crafted so CC uses consult_director (proactive path) AND might
    # still emit ambiguous-sounding language at turn end.  The important
    # assertion is that only ONE brain dispatch occurs per turn regardless.
    run = orch.run(Request(
        goal=(
            "You MUST call the consult_director tool first and ask it: "
            "'What should this utility function do?' "
            "After calling it, write a Python function based on the answer."
        )
    ))

    assert run.deliverable is not None and run.deliverable.content
    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE)

    hooks_log = exe.hooks_log()

    # Proactive path must have fired at least once.
    director_calls = filter_hook_events(hooks_log, hook="consult_director")
    assert len(director_calls) >= 1, (
        "consult_director was never called — proactive path not exercised. "
        "Hook log: " + str(hooks_log)
    )

    # For each turn where consult_director fired, the Stop hook must NOT have
    # also logged a halt_intercepted event — the lock prevented double-fire.
    halt_events = filter_hook_events(hooks_log, action="halt_intercepted")
    double_fire_candidates = []
    for dc in director_calls:
        # Find Stop events within 60 seconds of this consult_director call.
        for he in halt_events:
            if abs(he.get("ts", 0) - dc.get("ts", 0)) < 60:
                double_fire_candidates.append((dc, he))

    assert len(double_fire_candidates) == 0, (
        "Dispatch lock failed: consult_director AND Stop-hook both fired "
        "on the same turn. Double-fire candidates: " + str(double_fire_candidates)
    )
