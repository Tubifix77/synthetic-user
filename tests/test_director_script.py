"""The director as a script Claude runs through Bash (replaces the MCP server).

Company policy allows only official MCP servers, so `consult_director` is now
`python -m synthetic_user.director "question" "context"`. What must hold:

  - SYNTH_DIRECTOR_DISABLED=1 is the authoritative "off": the script answers
    "director unavailable" without calling the brain (scenario 3 relies on it;
    the Bash deny rule is only a safety net).
  - Every failure is an explicit "director unavailable" answer on stdout with
    exit 0 (FM-19) — never a traceback, never a hang.
  - The brain works to a deadline well under the tool timeout, so a slow
    triple-check ends with an answer instead of being killed partway.

FAST TEST — no LLM calls (the brain is made unreachable for real, not mocked).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from hooks.state import read_hooks_log
from synthetic_user import brain, config, director

_ROOT = Path(__file__).resolve().parents[1]


def _run(args, state_dir, *, extra_env=None, stdin=""):
    env = {k: v for k, v in os.environ.items() if k not in ("SYNTH_SESSION_DIR", "SYNTH_DIRECTOR_DISABLED")}
    if state_dir is not None:
        env["SYNTH_SESSION_DIR"] = str(state_dir)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-m", "synthetic_user.director", *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(_ROOT), timeout=60)


def test_disabled_switch_answers_unavailable_without_the_brain(tmp_path):
    r = _run(["Which format?"], tmp_path, extra_env={"SYNTH_DIRECTOR_DISABLED": "1",
                                                      "PATH": str(tmp_path / "no-such-bin")})
    assert r.returncode == 0
    assert r.stdout.lower().startswith("director unavailable")
    events = read_hooks_log(tmp_path)
    assert [e["action"] for e in events if e["hook"] == "consult_director"] == ["director_disabled"]
    assert not any(e["hook"] == "brain_dispatch" for e in events), "brain was called while disabled"
    assert not (tmp_path / "dispatch_lock.json").exists()


def test_unreachable_brain_answers_unavailable_not_a_traceback(tmp_path):
    r = _run(["Which format?", "context here"], tmp_path, extra_env={"PATH": str(tmp_path / "no-such-bin")})
    assert r.returncode == 0 and "Traceback" not in r.stdout + r.stderr
    assert r.stdout.lower().startswith("director unavailable")
    actions = [e["action"] for e in read_hooks_log(tmp_path) if e["hook"] == "consult_director"]
    assert actions == ["director_unavailable"]


def test_outside_a_run_it_does_nothing(tmp_path):
    r = _run(["Which format?"], None, extra_env={"PATH": str(tmp_path / "no-such-bin")})
    assert r.returncode == 0 and r.stdout.lower().startswith("director unavailable")


def test_question_can_come_from_stdin(tmp_path):
    r = _run([], tmp_path, stdin="Which format?\n\nsome context\n",
             extra_env={"SYNTH_DIRECTOR_DISABLED": "1"})
    event = [e for e in read_hooks_log(tmp_path) if e["hook"] == "consult_director"][0]
    assert event["question_preview"] == "Which format?"


def test_missing_question_is_an_explicit_answer(tmp_path):
    r = _run([], tmp_path)
    assert r.returncode == 0 and "no question" in r.stdout.lower()


def test_brain_honours_an_expired_deadline_without_calling_claude():
    t = time.monotonic()
    verdict = brain.dispatch("Should I delete the database? This is irreversible.",
                             deadline=time.monotonic() - 1)
    assert verdict.startswith("[brain") and "deadline" in verdict
    assert time.monotonic() - t < 2, "an expired deadline must not start a model call"


def test_timeout_budget_leaves_a_margin():
    # The hook sets DIRECTOR_TOOL_TIMEOUT_MS on every director call. It must sit
    # well above the director's own deadline (so the director always answers
    # first) and within the CLI's default Bash maximum of 600 000 ms.
    deadline_ms = config.DIRECTOR_DEADLINE_S * 1000
    assert config.DIRECTOR_TOOL_TIMEOUT_MS >= deadline_ms + 120_000
    assert config.DIRECTOR_TOOL_TIMEOUT_MS <= 600_000
    # The reactive path runs the same brain inside the Stop hook.
    settings = json.loads((_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    stop_timeout = settings["hooks"]["Stop"][0]["hooks"][0]["timeout"]
    assert stop_timeout * 1000 >= deadline_ms + 60_000


def test_director_command_is_what_the_instruction_and_grants_use():
    from hooks.session_start_handler import CONSULT_DIRECTOR_INSTRUCTION
    assert config.DIRECTOR_COMMAND in CONSULT_DIRECTOR_INSTRUCTION
    assert f"Bash({config.DIRECTOR_COMMAND}:*)" in config.EXECUTOR_ALLOWED_TOOLS
    assert director.__name__ == "synthetic_user.director"
