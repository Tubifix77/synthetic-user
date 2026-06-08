"""Shared vocabulary as types. Mirrors architecture2.md section 0 + components.

Walking-skeleton scope: just enough structure for scenario 1 to flow end-to-end.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Route(Enum):
    LOOP = "loop"        # send into the cycle loop
    SIMPLE = "simple"    # triage handles directly (weather/time/etc.) - later
    REJECT = "reject"    # malformed; return clarification - scenario 6


class StopCode(Enum):
    """Seeder terminal codes. Scenario 1 uses COMPLETE; scenario 2 REFINEMENT_COMPLETE.
    Full set lives in architecture2.md section 2.1."""
    COMPLETE = "complete"
    REFINEMENT_COMPLETE = "refinement_complete"


@dataclass
class Request:
    goal: str


@dataclass
class Deliverable:
    content: str
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Score:
    value: float
    passed: bool
    criteria_met: dict[str, bool] = field(default_factory=dict)


@dataclass
class SeederDecision:
    """Outcome of cycle-boundary reflection: either continue (with a direction)
    or stop (with a terminal code). Scenario 1: stop=COMPLETE after cycle 0."""
    stop: StopCode | None = None
    direction: str | None = None
    criteria: list[str] = field(default_factory=list)


@dataclass
class Cycle:
    index: int
    goal: str
    deliverable: Deliverable | None = None
    score: Score | None = None


@dataclass
class Run:
    request: Request
    route: Route
    cycles: list[Cycle] = field(default_factory=list)
    stop_code: StopCode | None = None
    reports: list = field(default_factory=list)
    rejected_reason: str | None = None

    @property
    def deliverable(self) -> Deliverable | None:
        return self.cycles[-1].deliverable if self.cycles else None

    @property
    def final_score(self) -> Score | None:
        return self.cycles[-1].score if self.cycles else None
