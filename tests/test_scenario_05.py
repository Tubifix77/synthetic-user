"""Scenario 5 (Steward fires compact intervention mid-cycle) - architecture2.md section 10.3.

Long-running cycle pushes counted tokens past the steward's threshold. The
PostToolUse handler detects the crossing and returns preservation guidance as
injected additionalContext so CC self-summarises in-turn. Cycle continues and
completes. Verifies: per-tool-call monitoring, token estimation, steward
intervention path, suggest_compact mechanism.

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


def test_scenario_05_steward_fires_suggest_compact():
    """Force threshold to 1 token so steward fires on the very first tool call.

    SYNTH_COMPACT_THRESHOLD_TOKENS=1 overrides the 60 % / 200 k default so the
    unit test does not need a genuinely long run to observe the behaviour.
    """
    exe = ClaudeCodeExecutor(extra_env={"SYNTH_COMPACT_THRESHOLD_TOKENS": "1"})
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    # Task that forces real tool execution within the project directory.
    # /tmp is blocked by CC permissions on this machine; use project-relative path.
    run = orch.run(Request(
        goal=(
            "Write a Python function that returns the square of a number. "
            "Save it to D:/AI/Synthetic/run_state/square_fn.py, "
            "then Read it back and confirm the content."
        )
    ))

    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE), (
        f"Run did not complete cleanly. stop_code={run.stop_code}, "
        f"cycles={len(run.cycles)}"
    )

    hooks_log = exe.hooks_log()

    # Steward must have fired at least one suggest_compact event.
    compact_events = filter_hook_events(hooks_log, action="suggest_compact")
    assert len(compact_events) >= 1, (
        "Steward never fired suggest_compact. "
        "Hook log: " + str(hooks_log)
    )

    # Each compact event should carry preservation_guidance.
    for ev in compact_events:
        assert ev.get("preservation_guidance"), (
            f"suggest_compact event missing preservation_guidance: {ev}"
        )


def test_scenario_05_steward_logs_routine_pings():
    """Even without threshold crossing, every PostToolUse call should log a ping."""
    exe = ClaudeCodeExecutor()
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    run = orch.run(Request(goal="write a hello world script"))

    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE)

    hooks_log = exe.hooks_log()

    # There should be PostToolUse pings recorded (even at normal token levels).
    ping_events = filter_hook_events(hooks_log, hook="PostToolUse")
    assert len(ping_events) >= 1, (
        "No PostToolUse pings in hooks_log — steward is not monitoring. "
        "Hook log: " + str(hooks_log)
    )
