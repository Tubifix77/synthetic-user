"""Steering brain (architecture2.md section 2.4).

Dispatch wrapper around the brain's core reasoning. Handles:
  - Routine cases: single-pass Sonnet call.
  - Hard-call escalation: triple-check (Pass 1 answer, Pass 2 critique + web,
    Pass 3 reconcile). Fires when the question contains irreversibility / low-
    confidence / destructive-operation signals.
  - Action verdicts: judge_action() gates a pending registered action
    (PreToolUse action patterns) with proceed / redirect / halt.
  - Dispatch lock: `in_triple_check` flag written to hooks_log prevents nested
    escalations while a triple-check is already running.

Logs a `brain_dispatch` event to hooks_log after every invocation so the
orchestrator can read it at cycle end and populate Decision Reports.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time

# When imported from hooks/ context, path is already inserted.
# When imported from synthetic_user/ context, add it here.
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hooks.state import log_hook_event
from synthetic_user.config import model_for
from synthetic_user.utils import extract_json_block

# ---------------------------------------------------------------------------
# Hard-call keywords — any of these in the question triggers triple-check.
# ---------------------------------------------------------------------------
_HARD_CALL_KEYWORDS = {
    "destructive",
    "irreversible",
    "cannot be undone",
    "delete",
    "drop",
    "low confidence",
    "uncertain",
    "dangerous",
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
_ROUTINE_PROMPT = """\
You are the steering brain of an autonomous software-development system.
A sub-task is asking for guidance. Provide a direct, actionable answer.
Do NOT ask follow-up questions. Make a definitive recommendation.

Question:
{question}
"""

_PASS1_PROMPT = """\
You are the steering brain of an autonomous software-development system.
A sub-task is asking for guidance on a hard, consequential decision.
Provide a thorough, well-reasoned answer.

Question:
{question}

Give your best answer now.
"""

_PASS2_PROMPT = """\
You are a critical reviewer examining a brain verdict.

Original question:
{question}

Pass 1 answer:
{pass1}

Critique this answer rigorously. Identify:
- Any assumptions that could be wrong
- Edge cases or risks not considered
- Whether the recommendation is genuinely safe or just convenient
Be adversarial. Find the weakest point.
"""

_PASS3_PROMPT = """\
You are the final arbiter reconciling two perspectives on a hard decision.

Original question:
{question}

Pass 1 answer (initial recommendation):
{pass1}

Pass 2 critique:
{pass2}

Synthesise a final verdict. Incorporate valid critique. Output a single
clear recommendation. Start with VERDICT: then give your answer.
"""


_CALL_TIMEOUT_S = 120   # one reasoning pass
_MIN_CALL_S = 5         # below this much budget, don't start a pass at all


def _claude_call(prompt: str, model: str | None = None, deadline: float | None = None) -> str:
    """Call `claude -p` and return the result text, or an error string.

    Strips SYNTH_SESSION_DIR so hooks on these internal calls are no-ops.
    stdin is DEVNULL: `claude -p` reads piped stdin and would block on an
    inherited pipe until the timeout.
    `deadline` (time.monotonic()) caps the call so the whole dispatch finishes
    inside its budget; past it, no call is started.
    """
    timeout = _CALL_TIMEOUT_S
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
        if timeout < _MIN_CALL_S:
            return "[brain error: director deadline reached]"
    env = {k: v for k, v in os.environ.items() if k != "SYNTH_SESSION_DIR"}
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model or model_for("director"),
             "--output-format", "json", "--dangerously-skip-permissions"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            return f"[brain error rc={r.returncode}: {r.stderr[:200]}]"
        return json.loads(r.stdout).get("result", "").strip()
    except Exception as exc:  # noqa: BLE001
        return f"[brain exception: {exc}]"


_ACTION_PROMPT = """\
You are the steering brain of an autonomous software-development system. The
agent doing the work is about to take a registered high-stakes action, and your
verdict gates it. No human is watching; you stand in for one.

Action pattern: {pattern}
What is about to happen: {summary}
Tool call: {tool_call}

The goal the agent was given:
{goal}

Decide:
  proceed  — the action is warranted by the goal; let it run.
  redirect — let it run, but the agent must first take your guidance into account.
  halt     — block it: not warranted by the goal, premature, or too risky to do unasked.

Pushing to a remote, adding a dependency or changing a schema that the goal did
not call for is usually a halt. Claiming done is a redirect unless the tool
output shows the work was verified.

Reply with JSON only, no markdown:
{{"verdict": "proceed"|"redirect"|"halt", "reason": "<one or two sentences addressed to the agent>"}}
"""


def judge_action(pattern: str, summary: str, tool_call: str, goal: str = "") -> dict:
    """Verdict on a pending registered action (PreToolUse, §2.9).

    Returns {"verdict": proceed|redirect|halt|unavailable, "reason": str}.
    "unavailable" means the brain could not produce a readable verdict; the
    caller must fail closed on it.
    """
    prompt = _ACTION_PROMPT.format(
        pattern=pattern, summary=summary, tool_call=tool_call[:1500],
        goal=goal[:1500] or "(not available)",
    )
    raw = _claude_call(prompt)
    verdict = {"verdict": "unavailable", "reason": raw[:300]}
    if not raw.startswith("[brain"):
        try:
            data = extract_json_block(raw)
            if data.get("verdict") in ("proceed", "redirect", "halt"):
                verdict = {"verdict": data["verdict"], "reason": str(data.get("reason", ""))}
        except (ValueError, AttributeError):
            pass
    log_hook_event({
        "hook": "brain_dispatch",
        "action": "action_verdict",
        "pattern": pattern,
        "verdict": verdict["verdict"],
        "verdict_preview": verdict["reason"][:300],
    })
    return verdict


def _is_hard_call(question: str) -> bool:
    q_lower = question.lower()
    return any(kw in q_lower for kw in _HARD_CALL_KEYWORDS)


def _in_triple_check() -> bool:
    """Check if a triple-check is already running (from env var, set by this process)."""
    return os.environ.get("SYNTH_IN_TRIPLE_CHECK") == "1"


def dispatch(question: str, context: str = "", deadline: float | None = None) -> str:
    """Main entry point. Returns the brain's verdict as a string, or an error
    string starting with "[brain" (callers turn that into "director unavailable").

    deadline: time.monotonic() by which the answer must exist; every pass is
    capped to the remaining budget (config.DIRECTOR_DEADLINE_S for callers).

    Logs a `brain_dispatch` event to hooks_log (readable by orchestrator
    at cycle end to populate Decision Reports).
    """
    full_question = question
    if context:
        full_question = f"{question}\n\nContext: {context}"

    if _is_hard_call(question) and not _in_triple_check():
        return _triple_check(full_question, deadline)
    else:
        return _routine(full_question, deadline)


def _routine(question: str, deadline: float | None = None) -> str:
    prompt = _ROUTINE_PROMPT.format(question=question)
    verdict = _claude_call(prompt, deadline=deadline)
    log_hook_event({
        "hook": "brain_dispatch",
        "action": "routine_dispatch",
        "triple_check_fired": False,
        "verdict_preview": verdict[:300],
    })
    return verdict


def _triple_check(question: str, deadline: float | None = None) -> str:
    # Set lock flag in environment so any nested call skips triple-check.
    os.environ["SYNTH_IN_TRIPLE_CHECK"] = "1"
    log_hook_event({
        "hook": "brain_dispatch",
        "action": "triple_check_lock_set",
    })

    try:
        # A fast tier by default: CC is blocked while the triple-check runs.
        _TC_MODEL = model_for("director_hard_call")
        passes: list[str] = []
        for template in (_PASS1_PROMPT, _PASS2_PROMPT, _PASS3_PROMPT):
            out = _claude_call(template.format(question=question, pass1=(passes + [""])[0],
                                               pass2=(passes + ["", ""])[1]),
                               model=_TC_MODEL, deadline=deadline)
            if out.startswith("[brain"):
                # Don't feed an error into the next pass; report it (FM-19).
                log_hook_event({"hook": "brain_dispatch", "action": "triple_check_aborted",
                                "failed_pass": len(passes) + 1, "error": out[:300]})
                return out
            passes.append(out)
        pass1, pass2, pass3 = passes

        # Extract the VERDICT line if present; else use full pass3.
        verdict = pass3
        for line in pass3.splitlines():
            if line.strip().upper().startswith("VERDICT:"):
                verdict = line.split(":", 1)[1].strip()
                break

        log_hook_event({
            "hook": "brain_dispatch",
            "action": "triple_check_complete",
            "triple_check_fired": True,
            "pass_1_output": pass1[:500],
            "pass_2_critique": pass2[:500],
            "pass_3_reconciliation": pass3[:500],
            "verdict_preview": verdict[:300],
        })
        return verdict

    finally:
        os.environ.pop("SYNTH_IN_TRIPLE_CHECK", None)
