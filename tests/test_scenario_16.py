"""Scenario 16 (Action-pattern trigger gates a registered action) - architecture2.md §2.9.

The framework is about to take a registered action (here: writing a dependency
manifest → `add_dependency`). The PreToolUse hook must recognise it, put it to
the live brain, and apply the verdict with the §2.9 mapping — before the tool
runs, and whether or not the framework chose to consult.

What is asserted, and why not more: the brain's verdict is a real model
judgement, so the test does not dictate proceed vs halt. It asserts that the
pattern fired, that the brain returned a readable verdict (not "unavailable"),
that the hook's decision matches the mapping for that verdict, and that the
file exists exactly when the decision allowed the write. The mapping and the
fail-closed path are pinned deterministically by tests/test_action_patterns.py
and tests/test_pre_tool_use_handler.py.

The action is chosen to be harmless under either verdict: a file under the
gitignored run_state/. (A live `git push` test is deliberately absent — this
repo's origin is real.)

INTEGRATION TEST — invokes a real `claude -p` subprocess plus one brain call.
"""
import uuid
from pathlib import Path

import pytest

from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[1]


def test_scenario_16_add_dependency_is_gated_by_the_brain():
    target = _ROOT / "run_state" / f"scenario16_{uuid.uuid4().hex[:8]}" / "requirements.txt"
    rel = target.relative_to(_ROOT).as_posix()
    exe = ClaudeCodeExecutor()
    exe.execute(
        f"Create the file {rel} containing exactly one line: requests==2.32.3 . "
        "Use the Write tool. Do not install anything and do not create any other files."
    )

    events = filter_hook_events(exe.hooks_log(), hook="PreToolUse", action="action_pattern")
    dep = [e for e in events if e.get("pattern") == "add_dependency"]
    assert dep, f"add_dependency never fired; PreToolUse events: {events or exe.hooks_log()}"

    first = dep[0]
    assert first["verdict"] in ("proceed", "redirect", "halt"), (
        f"brain returned no usable verdict (fail-closed path taken): {first}"
    )
    expected = "deny" if first["verdict"] == "halt" else "allow"
    assert first["decision"] == expected, f"verdict/decision mismatch: {first}"

    if all(e["decision"] == "deny" for e in dep):
        assert not target.exists(), "a denied write still happened"
    else:
        assert target.exists(), "an allowed write did not happen"
