"""PreToolUse handler wiring + FM-19 fail-closed on registered actions.

Scenario 14's design line: "PreToolUse denies the registered action patterns but
allows ordinary tools" when the director is unreachable. The director is made
unreachable for real (the `claude` binary is off PATH), not mocked.

FAST TEST — no LLM calls.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from hooks.state import read_hooks_log

_ROOT = Path(__file__).resolve().parents[1]
_HANDLER = str(_ROOT / "hooks" / "pre_tool_use_handler.py")


def _run(payload: dict, state_dir: Path, *, director_reachable: bool = True):
    env = {**os.environ, "SYNTH_SESSION_DIR": str(state_dir)}
    if not director_reachable:
        env["PATH"] = str(state_dir / "no-such-bin")
    r = subprocess.run([sys.executable, _HANDLER], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, timeout=60)
    out = json.loads(r.stdout) if r.stdout.strip() else None
    return r.returncode, out


def _decision(out):
    return out["hookSpecificOutput"]["permissionDecision"] if out else "allow"


def test_ordinary_tool_is_allowed_without_consulting(tmp_path):
    code, out = _run({"tool_name": "Bash", "tool_input": {"command": "ls"}}, tmp_path,
                     director_reachable=False)
    assert code == 0 and out is None
    assert [e["action"] for e in read_hooks_log(tmp_path)] == ["allow"]


def test_registered_action_fails_closed_when_director_unreachable(tmp_path):
    payload = {"tool_name": "Bash", "tool_input": {"command": "pip install requests"}}
    code, out = _run(payload, tmp_path, director_reachable=False)
    assert code == 0
    assert _decision(out) == "deny"
    assert "failing closed" in out["hookSpecificOutput"]["permissionDecisionReason"]
    events = [e for e in read_hooks_log(tmp_path) if e.get("action") == "action_pattern"]
    assert events and events[0]["pattern"] == "add_dependency"
    assert events[0]["verdict"] == "unavailable" and events[0]["decision"] == "deny"


def test_steward_interrupt_denies_any_tool(tmp_path):
    (tmp_path / "interrupt_flag.json").write_text(json.dumps({"active": True}))
    code, out = _run({"tool_name": "Read", "tool_input": {"file_path": "x"}}, tmp_path)
    assert code == 0 and _decision(out) == "deny"


def test_non_ascii_payload_still_reaches_the_guardrail(tmp_path):
    # Claude Code writes UTF-8. Decoding stdin with the Windows default (cp1252)
    # crashes on some bytes (e.g. "ŝ" → 0xC5 0x9D) — and a crash before matching
    # fails OPEN, silently skipping the guardrail.
    payload = {"tool_name": "Bash", "tool_input": {"command": "pip install requests  # ŝkip ønske"}}
    env = {**os.environ, "SYNTH_SESSION_DIR": str(tmp_path), "PATH": str(tmp_path / "no-such-bin"),
           "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    r = subprocess.run([sys.executable, _HANDLER], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       capture_output=True, env=env, timeout=60)
    out = json.loads(r.stdout) if r.stdout.strip() else None
    assert _decision(out) == "deny", "guardrail skipped on a non-ASCII payload"


def test_malformed_payload_allows(tmp_path):
    env = {**os.environ, "SYNTH_SESSION_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, _HANDLER], input="NOT JSON",
                       capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0 and r.stdout.strip() == ""


# ── director calls (the Bash-invoked replacement for the MCP tool) ─────────

def _director_payload(command, **extra):
    return {"tool_name": "Bash", "tool_input": {"command": command, "description": "ask", **extra}}


def test_director_call_gets_the_configured_timeout(tmp_path):
    from synthetic_user.config import DIRECTOR_COMMAND, DIRECTOR_TOOL_TIMEOUT_MS
    # Claude asked for a timeout that would cut a triple-check off mid-way.
    code, out = _run(_director_payload(f'{DIRECTOR_COMMAND} "Which format?"', timeout=120000), tmp_path)
    assert code == 0 and out is not None
    new = out["hookSpecificOutput"]["updatedInput"]
    assert new["timeout"] == DIRECTOR_TOOL_TIMEOUT_MS
    assert new["command"] == f'{DIRECTOR_COMMAND} "Which format?"' and new["description"] == "ask"
    assert "permissionDecision" not in out["hookSpecificOutput"], "the grant comes from --allowedTools, not the hook"
    assert [e["action"] for e in read_hooks_log(tmp_path)] == ["director_timeout_set"]


def test_director_call_is_never_judged_as_a_guardrail_action(tmp_path):
    from synthetic_user.config import DIRECTOR_COMMAND
    # The question mentions DDL; it must not be routed to the brain as modify_schema.
    code, out = _run(_director_payload(f'{DIRECTOR_COMMAND} "Should I CREATE TABLE users?"'), tmp_path,
                     director_reachable=False)
    assert out["hookSpecificOutput"].get("permissionDecision") is None
    assert not any(e.get("action") == "action_pattern" for e in read_hooks_log(tmp_path))
