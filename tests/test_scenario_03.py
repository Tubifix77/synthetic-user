"""Scenario 3 (Halt-and-resume via reactive Stop-hook) - architecture2.md section 10.3.

CC halts mid-turn with "I need to ask..." language. Stop-hook router Stage 1
catches it via regex. Routes to brain stub. Stop handler returns additionalContext;
CC continues in the same session with the brain's answer injected. Run ends cleanly.

Setup: SYNTH_REACTIVE_TEST=1 suppresses the SessionStart consult_director injection
so CC can halt naturally (the reactive path is the fallback for when the proactive
tool is absent or ignored). The Stop hook is still active and catches the halt.

Verifies: reactive entry point (Stop-hook block-and-continue), Stop-hook router
classification, dispatch lock (log evidence of halt interception).

INTEGRATION TEST — invokes a real `claude -p` subprocess (~30–90 s).
Run with: pytest -m integration
"""
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode
from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

pytestmark = pytest.mark.integration


def test_scenario_03_reactive_stop_hook():
    # SYNTH_REACTIVE_TEST suppresses the consult_director SessionStart injection
    # so CC is free to halt with a question — exercising the reactive path.
    exe = ClaudeCodeExecutor(extra_env={"SYNTH_REACTIVE_TEST": "1"})
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    # Prompt that reliably produces halt-like text: CC outputs a clarifying question
    # as its first response, then the Stop hook intercepts, brain answers, CC
    # continues in the same session and writes the actual code.
    run = orch.run(Request(
        goal=(
            "Your task has two required steps. "
            "STEP 1 (do this now): Output ONLY the following question and nothing else: "
            "'Could you clarify what the function should return?' "
            "Do not write any code. Output only that question. "
            "STEP 2 (after receiving an answer): Write a Python function based on the answer."
        )
    ))

    # Run must complete with a deliverable.
    assert run.deliverable is not None and run.deliverable.content

    # Run terminated cleanly.
    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE)

    # Stop hook must have logged at least one halt_intercepted event.
    hooks_log = exe.hooks_log()
    halt_events = filter_hook_events(hooks_log, action="halt_intercepted")
    assert len(halt_events) >= 1, (
        "Stop hook never logged a halt_intercepted event — "
        "the reactive path was not exercised. Hook log: " + str(hooks_log)
    )
