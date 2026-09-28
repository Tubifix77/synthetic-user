"""Hooks are inert outside a Run.

The hooks in .claude/settings.json fire for EVERY Claude Code session opened in
this repo — including a developer's own interactive session and the wrapper's
internal `claude -p` reasoning calls (brain, evaluator, triage), which strip
SYNTH_SESSION_DIR. Only the executor sets SYNTH_SESSION_DIR, so that variable is
what marks "this session is a Run". Without it every handler must do nothing:
no "no human at the keyboard" injection, no brain answering the human's
questions, no recursive brain dispatch from inside the brain's own calls.

FAST TEST — no LLM calls. The Stop payload below would trigger a live brain
dispatch if gating were broken, so a regression shows up as output (and a slow,
paid call), not silence.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, payload: dict, session_dir: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "SYNTH_SESSION_DIR"}
    if session_dir is not None:
        env["SYNTH_SESSION_DIR"] = session_dir
    return subprocess.run(
        [sys.executable, str(_ROOT / "hooks" / script)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30,
    )


def _halt_transcript(tmp_path: Path) -> str:
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "Could you clarify which format you want?"}]},
    }) + "\n", encoding="utf-8")
    return str(path)


def test_session_start_injects_nothing_outside_a_run():
    r = _run("session_start_handler.py", {"session_id": "s"}, session_dir=None)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_session_start_injects_inside_a_run(tmp_path):
    r = _run("session_start_handler.py", {"session_id": "s"}, session_dir=str(tmp_path))
    assert r.returncode == 0
    out = json.loads(r.stdout)
    from synthetic_user.config import DIRECTOR_COMMAND
    assert DIRECTOR_COMMAND in out["hookSpecificOutput"]["additionalContext"]


def test_stop_does_not_answer_the_humans_question_outside_a_run(tmp_path):
    payload = {"session_id": "s", "transcript_path": _halt_transcript(tmp_path)}
    r = _run("stop_handler.py", payload, session_dir=None)
    assert r.returncode == 0
    assert r.stdout.strip() == "", f"Stop hook acted outside a Run: {r.stdout[:300]}"


def test_empty_session_dir_counts_as_no_run():
    r = _run("session_start_handler.py", {"session_id": "s"}, session_dir="")
    assert r.stdout.strip() == ""


def test_pre_and_post_tool_use_are_silent_outside_a_run():
    payload = {"session_id": "s", "tool_name": "Bash",
               "tool_input": {"command": "pip install requests"}, "tool_response": {"stdout": "x" * 10_000}}
    for script in ("pre_tool_use_handler.py", "post_tool_use_handler.py"):
        r = _run(script, payload, session_dir=None)
        assert r.returncode == 0, script
        assert r.stdout.strip() == "", f"{script} acted outside a Run: {r.stdout[:300]}"
