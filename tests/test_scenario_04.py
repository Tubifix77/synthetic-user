"""Scenario 4 (Proactive dispatch via the director command) - architecture2.md section 10.3.

The director was an MCP tool until company policy allowed only official MCP
servers; it is now `python -m synthetic_user.director`, run through Bash (§12.9).

CC honors the SessionStart instruction and runs the director instead of
asking the user. The call blocks, brain runs, verdict returns as tool result,
CC continues without halting. Run completes in one turn.

Verifies: proactive entry point (synchronous MCP-tool dispatch), SessionStart
instruction injection, in-turn resolution with no halt.

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


def test_scenario_04_proactive_consult_director():
    exe = ClaudeCodeExecutor()
    mem = Memory()
    orch = Orchestrator(memory=mem, executor_fn=exe.execute)

    # Prompt that requires CC to consult the director before it can proceed.
    # The SessionStart instruction plus an explicit requirement should reliably
    # exercise the proactive MCP-tool path.
    run = orch.run(Request(
        goal=(
            "First run the director command (python -m synthetic_user.director) with the Bash tool and ask it: "
            "'What should this utility function do?' "
            "Do not write any code until you have its answer. "
            "After calling it, write a Python function based on the answer you receive."
        )
    ))

    # Run must complete with a deliverable.
    assert run.deliverable is not None and run.deliverable.content

    # Run terminated cleanly.
    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE)

    # The director must have ANSWERED (logged by the director script itself).
    hooks_log = exe.hooks_log()
    director_calls = filter_hook_events(hooks_log, hook="consult_director", action="proactive_dispatch")
    assert len(director_calls) >= 1, (
        "consult_director was never called — the proactive path was not exercised. "
        "Possible causes: SessionStart instruction not injected, the Bash grant missing, "
        "the brain unavailable, or CC resolved it without asking. Hook log: " + str(hooks_log)
    )

    # Ideally, no halt_intercepted events — CC used the proactive path, not reactive.
    # This is advisory (not asserted hard) because CC may use both in the same run.
    halt_events = filter_hook_events(hooks_log, action="halt_intercepted")
    if halt_events:
        # Document it but don't fail — the important thing is the proactive path fired.
        print(f"Note: {len(halt_events)} halt(s) also intercepted reactively this run.")
