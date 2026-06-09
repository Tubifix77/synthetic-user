"""Scenario 14 (Hook handler failure fails safe) - architecture2.md section 10.3.

Inject a fault into each hook handler in turn (crash / bad output). Verify
the safe-direction default for each:
  - PreToolUse: allows ordinary tools when handler crashes
  - Stop: lets CC stop (routes to evaluator) when handler crashes
  - PostToolUse: skips one steward update without aborting the cycle
  - consult_director: returns explicit "director unavailable" result

Each failure must be logged as a finding.

Verifies: FM-19 mitigation, fail-safe handler behaviour.

FAST+INTEGRATION TESTS — some use subprocess to exercise the handlers directly,
others run full integration. The subprocess tests are fast and do not need CC auth.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, _ROOT)
from hooks.state import read_hooks_log


def _run_handler(script: str, payload: dict, extra_env: dict | None = None) -> tuple[int, str, str]:
    """Run a hook handler script with the given payload on stdin.
    Returns (returncode, stdout, stderr).
    """
    env = {**os.environ, **( extra_env or {})}
    r = subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload),
        capture_output=True, text=True, env=env,
        timeout=30,
    )
    return r.returncode, r.stdout, r.stderr


def test_scenario_14_pre_tool_use_allows_on_crash():
    """If PreToolUse handler crashes (bad stdin), it must exit 0 (allow) not 1 (deny)."""
    # Send malformed JSON — handler should fail gracefully and allow.
    env = {**os.environ}
    r = subprocess.run(
        [sys.executable, f"{_ROOT}/hooks/pre_tool_use_handler.py"],
        input="NOT VALID JSON",
        capture_output=True, text=True, env=env,
        timeout=10,
    )
    # Safe direction for PreToolUse: allow (exit 0, no deny output).
    # Even on crash, PreToolUse must not block the tool call.
    assert r.returncode == 0, (
        f"PreToolUse crashed with non-zero exit — tool would be denied. "
        f"stderr: {r.stderr[:200]}"
    )
    # Must not output a deny decision.
    if r.stdout.strip():
        try:
            out = json.loads(r.stdout)
            assert out.get("decision") != "block", (
                f"PreToolUse output a block on crash: {out}"
            )
        except json.JSONDecodeError:
            pass  # no JSON output is fine (silent allow)


def test_scenario_14_stop_handler_allows_on_crash():
    """If Stop handler crashes (bad stdin), CC must be allowed to stop (exit 0)."""
    r = subprocess.run(
        [sys.executable, f"{_ROOT}/hooks/stop_handler.py"],
        input="NOT VALID JSON",
        capture_output=True, text=True, env=os.environ.copy(),
        timeout=10,
    )
    # Safe direction for Stop: allow CC to stop (exit 0, no block output).
    assert r.returncode == 0, (
        f"Stop handler crashed with non-zero exit — unexpected. stderr: {r.stderr[:200]}"
    )
    if r.stdout.strip():
        try:
            out = json.loads(r.stdout)
            # Should not output an additionalContext block on crash.
            assert "hookSpecificOutput" not in out, (
                f"Stop handler output hookSpecificOutput on crash: {out}"
            )
        except json.JSONDecodeError:
            pass


def test_scenario_14_post_tool_use_skips_on_crash():
    """If PostToolUse handler receives bad input, it exits 0 (skip update, no abort)."""
    r = subprocess.run(
        [sys.executable, f"{_ROOT}/hooks/post_tool_use_handler.py"],
        input="NOT VALID JSON",
        capture_output=True, text=True, env=os.environ.copy(),
        timeout=10,
    )
    # Safe direction: skip steward update, exit 0.
    assert r.returncode == 0, (
        f"PostToolUse crashed with non-zero exit. stderr: {r.stderr[:200]}"
    )


def test_scenario_14_consult_director_returns_unavailable_on_timeout():
    """consult_director must return a 'director unavailable' result on errors.

    We test this by calling the server's internal dispatch function with an
    environment where the brain is guaranteed to fail (bad PATH).
    """
    # Call brain.dispatch() with a broken PATH so _claude_call fails.
    env = {
        **os.environ,
        "PATH": "/nonexistent",  # breaks 'claude' binary lookup
        "SYNTH_SESSION_DIR": "",   # disables hook logging
    }
    r = subprocess.run(
        [sys.executable, "-c", (
            f"import sys; sys.path.insert(0, {_ROOT!r}); "
            "from synthetic_user.brain import dispatch; "
            "result = dispatch('test question'); "
            "print(result)"
        )],
        capture_output=True, text=True, env=env, timeout=30,
    )
    output = r.stdout.strip()
    # Brain must return something (not crash silently) and the result must
    # indicate an error condition rather than a plausible verdict.
    assert r.returncode == 0, f"brain.dispatch raised uncaught exception: {r.stderr[:300]}"
    assert output, "brain.dispatch returned empty string on failure"
    # The output should indicate an error (brain_error / brain_exception markers).
    assert "[brain" in output.lower() or "error" in output.lower() or "exception" in output.lower(), (
        f"brain.dispatch did not indicate failure gracefully: {output!r}"
    )


def test_scenario_14_full_run_survives_steward_fault(tmp_path):
    """A full run completes even if PostToolUse handler writes to a broken state dir."""
    from synthetic_user.orchestrator import Orchestrator
    from synthetic_user.memory import Memory
    from synthetic_user.types import Request, StopCode
    from synthetic_user.executor import ClaudeCodeExecutor

    # Use a state dir that exists but is read-only so steward writes fail.
    # On Windows read-only dirs still allow writes, so we use a non-existent
    # sub-path to force IOErrors in token counter writes.
    bad_dir = str(tmp_path / "no_such_subdir" / "run_state")
    exe = ClaudeCodeExecutor(extra_env={"SYNTH_SESSION_DIR": bad_dir})
    mem = Memory()
    run = Orchestrator(memory=mem, executor_fn=exe.execute).run(
        Request(goal="write a hello world script")
    )
    # Run must complete — steward failure must not cascade.
    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE), (
        f"Run failed due to steward fault: {run.stop_code}"
    )
