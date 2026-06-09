"""Scenario 3 (Halt-and-resume via reactive Stop-hook) - architecture2.md section 10.3.

CC halts mid-turn with question language. Stop-hook router Stage 1 catches it via
regex. Routes to brain stub. Stop handler returns additionalContext; CC continues
in the same session with the brain's answer injected.

Setup:
  - SYNTH_REACTIVE_TEST=1: suppresses the SessionStart consult_director injection
    so CC has no instruction to call that tool — it falls back to outputting a
    question as text.
  - --disallowed-tools mcp__synthetic-user__consult_director: removes the tool
    from the session entirely, eliminating the non-determinism between the MCP
    path and the halt-language path.

Verifies: reactive entry point (Stop-hook block-and-continue), Stop-hook router
classification, dispatch lock (log evidence of halt interception).

The assertion is strictly on halt_intercepted: the scenario's purpose is to
verify the reactive path fires, not to constrain the form of the final output.

INTEGRATION TEST — invokes a real `claude -p` subprocess (~30–90 s).
Run with: pytest -m integration
"""
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request
from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

pytestmark = pytest.mark.integration


def test_scenario_03_reactive_stop_hook():
    # SYNTH_REACTIVE_TEST suppresses the consult_director SessionStart injection.
    # --disallowed-tools removes consult_director from the tool list entirely so
    # CC has no choice but to output a question as text — the reactive path.
    exe = ClaudeCodeExecutor(
        extra_env={"SYNTH_REACTIVE_TEST": "1"},
        extra_flags=["--disallowed-tools", "mcp__synthetic-user__consult_director"],
    )
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    # Goal: names a concrete function (passes triage) but leaves the transformation
    # rule unspecified, so CC must ask before writing. CC's natural response is
    # "What should the function do?" / "What transformation..." — matches the halt
    # regex. The --disallowed-tools flag ensures CC can't route via consult_director.
    run = orch.run(Request(
        goal=(
            "Write a Python function called process_list(items). "
            "Before writing any code whatsoever, you must ask me "
            "one clarifying question about what transformation to apply. "
            "Do not write Python code until you receive an answer."
        )
    ))

    # The run must have reached CC at all (triage must have accepted it).
    assert run.cycles, (
        f"No cycles ran — triage may have rejected the goal. "
        f"rejected_reason: {run.rejected_reason}"
    )

    # Stop hook must have logged at least one halt_intercepted event.
    # This is the core assertion: the reactive path fired.
    hooks_log = exe.hooks_log()
    halt_events = filter_hook_events(hooks_log, action="halt_intercepted")
    assert len(halt_events) >= 1, (
        "Stop hook never logged a halt_intercepted event — "
        "the reactive path was not exercised. "
        "Hook log actions: " + str([e.get("action") for e in hooks_log])
    )
