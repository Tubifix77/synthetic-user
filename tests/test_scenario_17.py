"""Scenario 17 (Guardrails survive a change of directory) - hardening, 2026-09-28.

Hook commands used to be CWD-relative (`python hooks/<handler>.py`). Claude Code
runs hooks in the session's *current* directory, so after the framework ran
`cd somewhere` every hook failed to start — and a hook that fails to start is
non-blocking, i.e. the PreToolUse guardrail silently failed OPEN. Found by a
live Run whose own report said the PostToolUse hook "errored because it's
path-relative to the repo root".

The fix anchors every hook command on $CLAUDE_PROJECT_DIR. This scenario proves
it end to end: the framework changes directory, then attempts a registered
action; the guardrail must still see it.

The static half is a FAST test; the live half is INTEGRATION (a real `claude -p`
subprocess plus one brain call).
"""
import json
import uuid
from pathlib import Path

import pytest

from synthetic_user.executor import ClaudeCodeExecutor
from hooks.state import filter_hook_events

_ROOT = Path(__file__).resolve().parents[1]


def test_hook_commands_are_anchored_to_the_project_dir():
    # Fast, static half: every hook command must resolve without relying on CWD.
    settings = json.loads((_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for event, groups in settings["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                assert "$CLAUDE_PROJECT_DIR" in hook["command"], f"{event}: {hook['command']}"


@pytest.mark.integration
def test_scenario_17_guardrail_still_fires_after_cd():
    sub = _ROOT / "run_state" / f"scenario17_{uuid.uuid4().hex[:8]}"
    sub.mkdir(parents=True)
    rel = sub.relative_to(_ROOT).as_posix()
    exe = ClaudeCodeExecutor()
    exe.execute(
        f"First run exactly this shell command with the Bash tool: cd {rel} && ls . "
        "Then, from that same directory (do not cd back), use the Write tool to create "
        f"{rel}/requirements.txt containing exactly one line: requests==2.32.3 . "
        "Nothing else."
    )
    events = exe.hooks_log()
    bash = [e for e in filter_hook_events(events, hook="PostToolUse") if e.get("tool") == "Bash"]
    assert bash, f"the cd never ran, so this proves nothing; events: {events}"
    after_cd = [e for e in events if e["ts"] > bash[0]["ts"]]
    guarded = [e for e in after_cd if e.get("hook") == "PreToolUse" and e.get("action") == "action_pattern"]
    assert guarded and guarded[0]["pattern"] == "add_dependency", (
        f"guardrail did not fire after cd — hooks lost their path. events after cd: {after_cd}"
    )
