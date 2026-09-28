"""A failing Run stops as `circular` instead of retrying to the safety bound.

architecture2.md §2.1 defines `circular` — "lenses produce suggestions that
overlap with prior cycles' work". The v1 seeder stub never emitted it, so a
cycle the evaluator failed was retried with the same direction until
MAX_CYCLES_PER_RUN (25) — 25 full Claude Code cycles of quota on a Run that was
not converging. Found when the Layer-2 panel (correctly) failed a stub
deliverable and scenario 8 looped for 20+ minutes.

FAST TEST — no LLM calls (the seeder stub is pure).
"""
from synthetic_user import seeder
from synthetic_user.reports import ReportBuffer
from synthetic_user.types import Cycle, Request, Route, Run, Score, StopCode


def _failed(index: int, goal: str) -> Cycle:
    return Cycle(index=index, goal=goal, score=Score(value=0.1, passed=False))


def test_first_failure_gets_one_retry():
    run = Run(request=Request(goal="write a hello world script"), route=Route.LOOP)
    decision = seeder.reflect(_failed(0, "write a hello world script"), run, ReportBuffer())
    assert decision.stop is None and decision.direction


def test_failing_the_retry_too_is_circular():
    run = Run(request=Request(goal="write a hello world script"), route=Route.LOOP)
    first = seeder.reflect(_failed(0, "write a hello world script"), run, ReportBuffer())
    run.cycles.append(_failed(0, "write a hello world script"))
    decision = seeder.reflect(_failed(1, first.direction), run, ReportBuffer())
    assert decision.stop is StopCode.CIRCULAR


def test_a_pass_after_a_retry_still_completes():
    run = Run(request=Request(goal="write a hello world script"), route=Route.LOOP)
    first = seeder.reflect(_failed(0, "write a hello world script"), run, ReportBuffer())
    run.cycles.append(_failed(0, "write a hello world script"))
    passed = Cycle(index=1, goal=first.direction, score=Score(value=0.9, passed=True))
    assert seeder.reflect(passed, run, ReportBuffer()).stop is StopCode.COMPLETE
