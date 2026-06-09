"""Steering brain (architecture2.md section 2.4).

Dispatch wrapper around the brain's core reasoning. Handles:
  - Routine cases: single-pass Sonnet call.
  - Hard-call escalation: triple-check (Pass 1 answer, Pass 2 critique + web,
    Pass 3 reconcile). Fires when the question contains irreversibility / low-
    confidence / destructive-operation signals.
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

# When imported from hooks/ context, path is already inserted.
# When imported from synthetic_user/ context, add it here.
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hooks.state import log_hook_event

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


def _claude_call(prompt: str, model: str = "claude-sonnet-4-5") -> str:
    """Call `claude -p` and return the result text, or an error string.

    Strips SYNTH_SESSION_DIR so hooks on these internal calls are no-ops.
    """
    env = {k: v for k, v in os.environ.items() if k != "SYNTH_SESSION_DIR"}
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--output-format", "json", "--dangerously-skip-permissions"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if r.returncode != 0:
            return f"[brain error rc={r.returncode}: {r.stderr[:200]}]"
        return json.loads(r.stdout).get("result", "").strip()
    except Exception as exc:  # noqa: BLE001
        return f"[brain exception: {exc}]"


def _is_hard_call(question: str) -> bool:
    q_lower = question.lower()
    return any(kw in q_lower for kw in _HARD_CALL_KEYWORDS)


def _in_triple_check() -> bool:
    """Check if a triple-check is already running (from env var, set by this process)."""
    return os.environ.get("SYNTH_IN_TRIPLE_CHECK") == "1"


def dispatch(question: str, context: str = "") -> str:
    """Main entry point. Returns the brain's verdict as a string.

    Logs a `brain_dispatch` event to hooks_log (readable by orchestrator
    at cycle end to populate Decision Reports).
    """
    full_question = question
    if context:
        full_question = f"{question}\n\nContext: {context}"

    if _is_hard_call(question) and not _in_triple_check():
        return _triple_check(full_question)
    else:
        return _routine(full_question)


def _routine(question: str) -> str:
    prompt = _ROUTINE_PROMPT.format(question=question)
    verdict = _claude_call(prompt)
    log_hook_event({
        "hook": "brain_dispatch",
        "action": "routine_dispatch",
        "triple_check_fired": False,
        "verdict_preview": verdict[:300],
    })
    return verdict


def _triple_check(question: str) -> str:
    # Set lock flag in environment so any nested call skips triple-check.
    os.environ["SYNTH_IN_TRIPLE_CHECK"] = "1"
    log_hook_event({
        "hook": "brain_dispatch",
        "action": "triple_check_lock_set",
    })

    try:
        # Use Haiku for passes to minimise latency while triple-check is blocking CC.
        _TC_MODEL = "claude-haiku-4-5"
        pass1 = _claude_call(_PASS1_PROMPT.format(question=question), model=_TC_MODEL)
        pass2 = _claude_call(_PASS2_PROMPT.format(question=question, pass1=pass1), model=_TC_MODEL)
        pass3 = _claude_call(_PASS3_PROMPT.format(
            question=question, pass1=pass1, pass2=pass2
        ), model=_TC_MODEL)

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
