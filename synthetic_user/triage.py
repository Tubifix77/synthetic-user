"""Triage gate (architecture2.md section 2.0).

Stage 1: rule-based pre-filter (empty / blank goal → reject immediately).
Stage 2: Haiku LLM classifier — rejects vague/malformed requests that passed
         Stage 1 but are too underspecified to send into the loop.

architecture2.md section 2.0: triage must never start a cycle on a request
that the system cannot complete in good faith.
"""
from __future__ import annotations
import json
import os
import subprocess
from synthetic_user.types import Request, Route
from synthetic_user.reports import DecisionReport, ReportBuffer

# ---------------------------------------------------------------------------
# Stage-2 prompt
# ---------------------------------------------------------------------------
_CLASSIFY_PROMPT = """\
You are a request classifier for an autonomous software-development agent.
Classify the following user request into exactly one of two categories:

LOOP   — A reasonable software agent can attempt this without further
          clarification. The goal names a recognisable software artefact or
          task (script, function, program, API, bug fix, refactoring, test,
          docs, etc.) and a competent developer could start work immediately
          by making sensible default choices. Missing minor details (language,
          output path, style) do NOT justify rejection.
          Examples: "write a hello world script", "sort a list of numbers",
          "build a REST API", "fix the login bug".

REJECT — The request has no discernible software deliverable or is so
          underspecified that even picking a starting point is impossible.
          Reject only when a developer would stare blankly and have no idea
          what artifact to produce. Examples: "write me something interesting",
          "do something cool", "surprise me".

Err on the side of LOOP. Only reject genuinely unactionable requests.

Reply with a JSON object and NOTHING else — no markdown fences, no commentary:
{{"route": "loop"|"reject", "reason": "<one sentence explaining the decision>"}}

User request:
{goal}
"""


def _stage2_classify(goal: str) -> tuple[str, str]:
    """Call Haiku to classify. Returns (route, reason). Falls back to 'loop' on error."""
    prompt = _CLASSIFY_PROMPT.format(goal=goal)
    env = {k: v for k, v in os.environ.items() if k != "SYNTH_SESSION_DIR"}
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", "claude-haiku-4-5",
                "--output-format", "json",
                "--dangerously-skip-permissions",
            ],
            capture_output=True, text=True, timeout=60, env=env,
        )
        if result.returncode != 0:
            return "loop", f"stage2 error (rc={result.returncode}), defaulting to loop"

        outer = json.loads(result.stdout)
        inner_text = (outer.get("result") or "").strip()

        # Strip markdown fences if the model adds them anyway
        if inner_text.startswith("```"):
            inner_text = inner_text.split("```")[1]
            if inner_text.startswith("json"):
                inner_text = inner_text[4:]
            inner_text = inner_text.strip()

        inner = json.loads(inner_text)
        route = inner.get("route", "loop").strip().lower()
        reason = inner.get("reason", "")
        if route not in ("loop", "reject"):
            route = "loop"
        return route, reason
    except Exception as exc:  # noqa: BLE001
        return "loop", f"stage2 exception: {exc}"


def triage(request: Request, buffer: ReportBuffer) -> tuple[Route, str | None]:
    """Return (route, rejected_reason). rejected_reason is None for non-REJECT routes."""
    # ------------------------------------------------------------------
    # Stage 1: rule-based (cost-free)
    # ------------------------------------------------------------------
    if not request.goal or not request.goal.strip():
        buffer.add(DecisionReport(
            component="triage", decision_type="route",
            selected="reject",
            rationale="stage-1 rule: empty goal",
            component_specific={"stage_reached": 1},
        ))
        return Route.REJECT, "Request is empty. Please provide a goal."

    # ------------------------------------------------------------------
    # Stage 2: Haiku LLM classifier
    # ------------------------------------------------------------------
    raw_route, reason = _stage2_classify(request.goal)
    route = Route.REJECT if raw_route == "reject" else Route.LOOP

    buffer.add(DecisionReport(
        component="triage", decision_type="route",
        selected=route.value,
        rationale=reason or f"stage-2 haiku classified as {raw_route}",
        component_specific={"stage_reached": 2},
    ))

    if route is Route.REJECT:
        return Route.REJECT, reason or "Request is too vague or out of scope."
    return Route.LOOP, None
