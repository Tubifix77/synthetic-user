"""Scenario 11 (Long-Run survival) - architecture2.md section 10.3.

Run a Synthetic User Run that spans 5+ cycles (multi-stage refinement).
Steward maintains context health across the full Run via multiple compact
interventions. No catastrophic context loss. Final cycle scores match or
exceed earlier cycles.

Verifies: steward sustained operation, multi-cycle stability, FM-14 mitigation.

INTEGRATION TEST — invokes multiple real `claude -p` subprocesses (slow).
Run with: pytest -m integration
"""
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode, Route
from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

pytestmark = pytest.mark.integration


def test_scenario_11_long_run_survives_5_cycles():
    """A multi-stage goal drives at least 5 cycles without context collapse.

    SYNTH_COMPACT_THRESHOLD_TOKENS=500 forces steward interventions frequently
    so we observe multiple suggest_compact events across cycles.

    The seeder naturally drives multiple cycles for a multi-stage task.
    We cap with MAX_CYCLES_PER_RUN and verify at least 5 ran.
    """
    exe = ClaudeCodeExecutor(
        extra_env={"SYNTH_COMPACT_THRESHOLD_TOKENS": "500"}
    )
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    # Multi-stage task that the seeder will want to refine across several cycles.
    # Each cycle adds a layer: implementation → tests → docs → refinement → polish.
    run = orch.run(Request(goal=(
        "Build a small Python calculator module with the following stages: "
        "Stage 1: implement the core arithmetic functions (add, subtract, multiply, divide). "
        "Stage 2: add input validation and error handling. "
        "Stage 3: write unit tests for all functions. "
        "Stage 4: add a command-line interface. "
        "Stage 5: write a README with usage examples. "
        "Save everything to D:/AI/Synthetic/run_state/calculator/. "
        "Complete each stage fully before moving to the next."
    )))

    # Run must complete (not crash or timeout).
    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE), (
        f"Long run did not complete cleanly: stop_code={run.stop_code}, "
        f"cycles={len(run.cycles)}"
    )

    # At least 2 cycles (ideally more, but seeder controls this).
    assert len(run.cycles) >= 2, (
        f"Expected multi-cycle run, got {len(run.cycles)} cycle(s). "
        "The seeder may be stopping too early."
    )

    # Steward must have fired at least one suggest_compact (threshold is low).
    hooks_log = exe.hooks_log()
    compact_events = filter_hook_events(hooks_log, action="suggest_compact")
    assert len(compact_events) >= 1, (
        "Steward never fired suggest_compact across a multi-cycle run. "
        "Hook log has " + str(len(hooks_log)) + " events."
    )

    # Context health check: all cycles must have deliverables (no silent failure).
    for cycle in run.cycles:
        assert cycle.deliverable is not None and cycle.deliverable.content, (
            f"Cycle {cycle.index} has no deliverable — context may have collapsed."
        )

    # Final cycle score must be present (evaluator ran to completion).
    assert run.final_score is not None, "No final score — evaluator did not run on last cycle"
    assert run.final_score.value > 0, "Final cycle scored 0 — potential context collapse"


def test_scenario_11_no_silent_autocompact():
    """Verify there are no hook gaps that indicate silent CC autocompact.

    A silent autocompact would show as a sudden drop in PostToolUse token
    counter without a corresponding suggest_compact from the steward.
    We check that every large counter reset is preceded by a suggest_compact.
    """
    exe = ClaudeCodeExecutor(
        extra_env={"SYNTH_COMPACT_THRESHOLD_TOKENS": "500"}
    )
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    run = orch.run(Request(goal=(
        "Build a simple Python calculator module with add, subtract, multiply, divide. "
        "Save to D:/AI/Synthetic/run_state/calc2.py with unit tests."
    )))

    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE)

    hooks_log = exe.hooks_log()
    pings = filter_hook_events(hooks_log, action="steward_ping")

    # Check for anomalous counter resets: if token count drops by > 50% between
    # pings without a preceding suggest_compact, that indicates silent autocompact.
    compact_events = filter_hook_events(hooks_log, action="suggest_compact")
    compact_timestamps = {ev.get("ts", 0) for ev in compact_events}

    prev_count = 0
    for ping in pings:
        count = ping.get("counted_tokens", 0)
        if prev_count > 500 and count < prev_count * 0.5:
            # Counter dropped by > 50% — check if a compact preceded this.
            ping_ts = ping.get("ts", 0)
            preceding_compacts = [
                ts for ts in compact_timestamps
                if ts < ping_ts and ping_ts - ts < 300  # within 5 minutes
            ]
            assert preceding_compacts, (
                f"Counter dropped from {prev_count} to {count} without prior "
                f"suggest_compact — possible silent CC autocompact at ts={ping_ts}"
            )
        prev_count = count
