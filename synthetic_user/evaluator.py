"""Evaluator (architecture2.md section 2.5).

Three-layer hybrid:
  Layer 1 — Rule-based score (fast, cheap). Passes non-empty deliverables.
  Layer 2 — Multi-hat panel (fires when Layer 1 score < anomaly_threshold).
             Hats: Correctness (Sonnet), Adversary (Haiku — tier diversity),
             User-intent (Sonnet). Each cites evidence. Adversary holds veto.
             Inter-hat disagreement → panel_confidence signal.
  Layer 3 — Classifier update (threshold weights; stub in v1).

SOLE memory writer (architecture2.md section 2.6).

Anomaly threshold: default 0.5; override with SYNTH_EVAL_ANOMALY_THRESHOLD env var
(useful for testing Layer 2 without a genuinely bad deliverable).
"""
from __future__ import annotations
import json
import os
import subprocess
from synthetic_user.types import Cycle, Score
from synthetic_user.reports import DecisionReport, ReportBuffer
from synthetic_user.memory import Memory

_DEFAULT_ANOMALY_THRESHOLD = 0.5


def _anomaly_threshold() -> float:
    try:
        return float(os.environ.get("SYNTH_EVAL_ANOMALY_THRESHOLD", _DEFAULT_ANOMALY_THRESHOLD))
    except ValueError:
        return _DEFAULT_ANOMALY_THRESHOLD


def _claude(prompt: str, model: str = "claude-sonnet-4-5") -> str:
    """Internal LLM call. Strips SYNTH_SESSION_DIR so hooks become no-ops."""
    env = {k: v for k, v in os.environ.items() if k != "SYNTH_SESSION_DIR"}
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--output-format", "json", "--dangerously-skip-permissions"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        if r.returncode != 0:
            return f"[evaluator error rc={r.returncode}]"
        return json.loads(r.stdout).get("result", "").strip()
    except Exception as exc:  # noqa: BLE001
        return f"[evaluator exception: {exc}]"


# ---------------------------------------------------------------------------
# Layer 2 hat prompts
# ---------------------------------------------------------------------------
_HAT_PROMPT = """\
You are the {hat_name} evaluator hat in a multi-perspective review panel.

Goal (what was requested):
{goal}

Deliverable (what was produced):
{deliverable}

Your role:
{role_desc}

Rules:
1. You MUST cite at least one concrete piece of evidence (a specific line, missing
   feature, test case, or observed behaviour) to support your judgment.
2. Output JSON only — no markdown fences, no commentary:
   {{"verdict": "pass"|"fail"|"uncertain", "evidence": "<one sentence of concrete evidence>", "assessment": "<2-3 sentence evaluation>"}}
"""

_HAT_ROLES = {
    "correctness": (
        "Correctness — Did the deliverable do exactly what was requested? "
        "Check for functional accuracy, completeness, and whether it actually runs/works."
    ),
    "adversary": (
        "Adversary — What is wrong, missing, unverified, or faked? "
        "Find the weakest point. Be sceptical. Assume optimistic claims are unverified."
    ),
    "user_intent": (
        "User-intent — Does the deliverable serve what was actually wanted, "
        "not just the literal request? Check for the spirit of the goal, not just the letter."
    ),
}

_HAT_MODELS = {
    "correctness": "claude-sonnet-4-5",
    "adversary": "claude-haiku-4-5",   # different tier for bias diversity (arch section 2.5)
    "user_intent": "claude-sonnet-4-5",
}


def _run_hat(hat_name: str, goal: str, deliverable_text: str) -> dict:
    """Run one evaluation hat. Returns dict with verdict, evidence, assessment."""
    prompt = _HAT_PROMPT.format(
        hat_name=hat_name.replace("_", "-").title(),
        goal=goal,
        deliverable=deliverable_text[:2000],
        role_desc=_HAT_ROLES[hat_name],
    )
    raw = _claude(prompt, model=_HAT_MODELS[hat_name])
    # Strip markdown fences if model adds them.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
        verdict = data.get("verdict", "uncertain")
        if verdict not in ("pass", "fail", "uncertain"):
            verdict = "uncertain"
        return {
            "verdict": verdict,
            "evidence": data.get("evidence", ""),
            "assessment": data.get("assessment", ""),
        }
    except Exception:  # noqa: BLE001
        # Graceful degradation: return uncertain so the panel can still conclude.
        return {"verdict": "uncertain", "evidence": raw[:200] if raw else "[no output]", "assessment": ""}


def _layer2_panel(cycle: Cycle) -> dict:
    """Run the three-hat panel. Returns component_specific dict for the report."""
    goal = cycle.goal
    deliverable_text = cycle.deliverable.content if cycle.deliverable else ""

    hats = {
        name: _run_hat(name, goal, deliverable_text)
        for name in ["correctness", "adversary", "user_intent"]
    }

    # Adversary veto: if adversary says fail, panel conclusion is fail.
    adversary_verdict = hats["adversary"]["verdict"]
    if adversary_verdict == "fail":
        panel_conclusion = "fail"
    else:
        # Majority vote among all three hats.
        votes = [h["verdict"] for h in hats.values()]
        pass_count = votes.count("pass")
        fail_count = votes.count("fail")
        if fail_count > pass_count:
            panel_conclusion = "fail"
        elif pass_count > fail_count:
            panel_conclusion = "pass"
        else:
            panel_conclusion = "uncertain"

    # Confidence = 1 - disagreement_rate (proportion of hats that differ from conclusion).
    disagreement = sum(
        1 for v in [h["verdict"] for h in hats.values()] if v != panel_conclusion
    ) / len(hats)
    panel_confidence = round(1.0 - disagreement, 3)

    return {
        "hats": hats,
        "panel_conclusion": panel_conclusion,
        "panel_confidence": panel_confidence,
    }


# ---------------------------------------------------------------------------
# Dispatch-escape audit (FM-18)
# ---------------------------------------------------------------------------
_ESCAPE_PROMPT = """\
You are an audit classifier for an autonomous software agent.

Goal (what was requested):
{goal}

Deliverable (what was produced — excerpt):
{deliverable}

Task: Determine whether the agent made a CONSEQUENTIAL DESIGN CHOICE that the
specification EXPLICITLY left open, without consulting the user for clarification.

A choice qualifies as a dispatch escape ONLY if ALL of the following hold:
1. The spec EXPLICITLY signalled that a choice was open — words like "unspecified",
   "choose as you see fit", "any format", "your choice", "decide", "either … or".
   (If the spec made no mention of the dimension at all, that is NOT an escape.)
2. The agent silently resolved that open dimension without asking.
3. The choice materially affects the output in a way that could surprise the
   requester (e.g., chose JSON vs CSV when spec said "some format").

Do NOT flag:
- Language or technology choices implied by the task ("write a Python script"
  → Python is implied; "write a script" → any scripting language is fine).
- Style choices (variable names, indentation, comment style).
- Choices that any reasonable developer would make without asking (e.g., using
  newlines between list items, returning integers not strings for numeric output).
- Choices where only ONE reasonable option exists.

If in doubt, return false — only flag CLEAR, EXPLICIT open choices.

Reply with JSON only — no markdown, no commentary:
{{"escape": true|false, "description": "<one sentence: what open choice was made silently, or 'none'>"}}
"""


def _dispatch_escape_audit(cycle: Cycle) -> tuple[bool, str]:
    """Ask Haiku whether the cycle made a consequential unescalated choice.

    Returns (is_escape, description). Fails safe to (False, "") on error.
    """
    goal = cycle.goal
    deliverable_text = (cycle.deliverable.content if cycle.deliverable else "")[:2000]
    prompt = _ESCAPE_PROMPT.format(goal=goal, deliverable=deliverable_text)
    raw = _claude(prompt, model="claude-haiku-4-5")
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
        is_escape = bool(data.get("escape", False))
        desc = data.get("description", "")
        return is_escape, desc
    except Exception:  # noqa: BLE001
        return False, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(cycle: Cycle, criteria: list[str], buffer: ReportBuffer) -> Score:
    """Layer 1 + optional Layer 2 evaluation."""
    has_deliverable = cycle.deliverable is not None and bool(cycle.deliverable.content)
    layer1_score = 0.9 if has_deliverable else 0.0
    threshold = _anomaly_threshold()

    anomaly = layer1_score < threshold
    layer2_disabled = os.environ.get("SYNTH_EVAL_LAYER2_DISABLED") == "1"
    layer2_data: dict | None = None

    if anomaly and not layer2_disabled:
        try:
            layer2_data = _layer2_panel(cycle)
            # Adjust the score downward if the panel concludes fail.
            if layer2_data.get("panel_conclusion") == "fail":
                layer1_score = 0.1
        except Exception as exc:  # noqa: BLE001
            # FM-17: evaluator audits its own faults rather than crashing.
            buffer.add(DecisionReport(
                component="evaluator", decision_type="evaluator_fault",
                selected="layer2_skipped",
                rationale=f"Layer 2 panel raised exception: {exc!r}",
                confidence="low", self_reported=True,
                audit_flags=["layer2_fault"],
            ))

    score = Score(
        value=layer1_score,
        passed=layer1_score >= 0.5,
        criteria_met={c: layer1_score >= 0.5 for c in (criteria or ["deliverable exists"])},
    )

    # Layer 1 + self-report.
    buffer.add(DecisionReport(
        component="evaluator", decision_type="reliability_eval",
        selected="pass" if score.passed else "fail",
        rationale=f"layer-1 score={layer1_score:.2f}, threshold={threshold}",
        confidence="high" if not anomaly else "low",
        self_reported=True,
        component_specific={
            "score": layer1_score,
            "anomaly_detected": anomaly,
            "layer2_fired": layer2_data is not None,
        },
    ))

    # Dispatch-escape audit (FM-18) — runs on every cycle; fails safe to (False, "").
    try:
        is_escape, escape_desc = _dispatch_escape_audit(cycle)
    except Exception as exc:  # noqa: BLE001
        is_escape, escape_desc = False, ""
        buffer.add(DecisionReport(
            component="evaluator", decision_type="evaluator_fault",
            selected="escape_audit_skipped",
            rationale=f"Dispatch-escape audit raised exception: {exc!r}",
            confidence="low", self_reported=True,
            audit_flags=["escape_audit_fault"],
        ))
    if is_escape:
        buffer.add(DecisionReport(
            component="evaluator",
            decision_type="dispatch_escape",
            selected="flagged",
            rationale=escape_desc or "agent made a consequential unescalated choice",
            confidence="medium",
            audit_flags=["dispatch_escape"],
            self_reported=True,
        ))

    # Layer 2 panel report (if fired).
    if layer2_data is not None:
        panel_conclusion = layer2_data.get("panel_conclusion", "uncertain")
        buffer.add(DecisionReport(
            component="evaluator",
            decision_type="layer2_panel",
            selected=panel_conclusion,
            rationale=(
                f"multi-hat panel: adversary={layer2_data['hats']['adversary']['verdict']}, "
                f"correctness={layer2_data['hats']['correctness']['verdict']}, "
                f"user_intent={layer2_data['hats']['user_intent']['verdict']}"
            ),
            confidence=str(layer2_data.get("panel_confidence", 0.5)),
            audit_flags=(["panel_fired"] if anomaly else []),
            self_reported=True,
            component_specific=layer2_data,
        ))

    return score


def ingest_reports(buffer: ReportBuffer, memory: Memory) -> int:
    """Evaluator-mediated write (section 2.6/2.8): drain buffer -> validate -> persist."""
    return memory.write_reports(buffer.drain())
