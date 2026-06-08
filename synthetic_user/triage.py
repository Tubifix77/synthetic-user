"""Triage gate (architecture2.md section 2.0). Walking-skeleton: Stage-1 rule only.
Stage-2 Haiku and Stage-3 fallback come later (TBD-9)."""
from __future__ import annotations
from synthetic_user.types import Request, Route
from synthetic_user.reports import DecisionReport, ReportBuffer


def triage(request: Request, buffer: ReportBuffer) -> Route:
    route = Route.REJECT if not request.goal or not request.goal.strip() else Route.LOOP
    buffer.add(DecisionReport(
        component="triage", decision_type="route",
        selected=route.value, rationale="stage-1 rule: non-empty goal -> loop",
        component_specific={"stage_reached": 1},
    ))
    return route
