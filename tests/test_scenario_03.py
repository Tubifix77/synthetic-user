"""Scenario 3 (Halt-and-resume via reactive Stop-hook) - architecture2.md section 10.3.

CC halts mid-turn with question language. The Stop-hook router Stage 1 catches it
via regex, invokes the brain, and returns additionalContext so CC continues in the
same session with the brain's answer injected.

What this scenario proves: the *reactive Stop-hook path* fires end-to-end — CC
halts with a question, the router classifies it as a halt, the brain is invoked
(block), AND the session resumes with the answer injected (continue). The proof
is two hook-log events: `halt_intercepted` (block) followed by `allow_passthrough`
(the second Stop fire after CC resumed — continue).

Why this test drives the executor directly (not Orchestrator.run()):
  Orchestrator.run() calls triage first, and triage is itself a live-LLM judgment.
  Routing through it made this scenario depend on TWO independent model calls both
  landing the right way in one run — triage accepting a deliberately-underspecified
  goal AND CC organically halting. Those pull against each other (a goal vague
  enough to make CC ask is exactly what triage is inclined to reject), which is
  what made the test flaky. Triage's accept/reject behaviour is not what scenario 3
  is testing — scenario 6 covers triage. So we exercise the executor + Stop-hook
  path directly and remove triage from the equation entirely.

Determinism aids (all retained):
  - SYNTH_REACTIVE_TEST=1: suppresses the SessionStart consult_director injection
    so CC has no instruction to call that tool — it outputs a question as text.
  - --disallowed-tools mcp__synthetic-user__consult_director: removes the tool from
    the session entirely, so CC cannot route via the proactive path.
  - The goal specifies the exact clarifying question for CC to emit. That question
    matches the halt regex, so detection is deterministic; the only model behaviour
    relied upon is compliance with "ask this first, don't code yet", which is
    strong and was verified consistent across repeated live runs.

INTEGRATION TEST — invokes a real `claude -p` subprocess (~60–130 s; the brain's
reactive answer is itself a live model call).
Run with: pytest -m integration
"""
import pytest
from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

pytestmark = pytest.mark.integration


# A clearly-a-software-task goal (so CC engages) that withholds the transformation
# rule and instructs CC to emit one specific clarifying question first. The exact
# question is dictated so the halt regex matches deterministically; CC's only job
# is to comply with asking before coding.
_GOAL = (
    "You are to write a Python function called process_list(items). "
    "The transformation it must apply has deliberately NOT been specified. "
    "Your FIRST response must be exactly this clarifying question and nothing else:\n"
    '"Could you clarify what transformation the function should apply to each item?"\n'
    "Do not write any code until you receive an answer."
)


def test_scenario_03_reactive_stop_hook():
    # Drive the executor directly — no Orchestrator, no triage in the path.
    exe = ClaudeCodeExecutor(
        extra_env={"SYNTH_REACTIVE_TEST": "1"},
        extra_flags=["--disallowed-tools", "mcp__synthetic-user__consult_director"],
    )

    # One CC session. CC emits the clarifying question; the Stop hook intercepts it,
    # the brain answers, and CC continues in the same session — all within this call.
    exe.execute(_GOAL)

    hooks_log = exe.hooks_log()
    actions = [e.get("action") for e in hooks_log]

    # (1) The halt was intercepted: the router classified CC's question as a halt
    #     and the brain was invoked (block half of block-and-continue).
    halt_events = filter_hook_events(hooks_log, action="halt_intercepted")
    assert len(halt_events) >= 1, (
        "Stop hook never logged a halt_intercepted event — the reactive path was "
        "not exercised. Hook log actions: " + str(actions)
    )

    # (2) The session actually CONTINUED past the block. After the Stop hook blocks
    #     once, CC resumes with the injected answer and stops again; that second Stop
    #     carries stop_hook_active=True and is logged as allow_passthrough. Its
    #     presence is deterministic proof of the "continue" half — without it, a run
    #     that blocked but failed to resume would pass on (1) alone (a false pass).
    passthrough_events = filter_hook_events(hooks_log, action="allow_passthrough")
    assert len(passthrough_events) >= 1, (
        "Stop hook intercepted the halt but logged no allow_passthrough — CC did not "
        "resume past the block, so block-and-continue was not proven. "
        "Hook log actions: " + str(actions)
    )
