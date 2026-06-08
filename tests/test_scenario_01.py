"""Scenario 1 (walking skeleton) - architecture2.md section 10.3.

Cold-start request -> triage LOOP -> seeder pass-through -> executor produces a
deliverable -> evaluator scores high -> seeder converges to COMPLETE -> Run ends
cleanly with Decision Reports written to memory.

Verifies: walking skeleton, data flow end-to-end, evaluator-mediated report writes.
"""
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode
from synthetic_user import config


def test_scenario_01_simple_successful_run():
    mem = Memory()
    run = Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    # data flowed end-to-end: at least one cycle, with a deliverable
    assert len(run.cycles) >= 1
    assert run.deliverable is not None and run.deliverable.content

    # evaluator scored above threshold
    assert run.final_score is not None
    assert run.final_score.passed
    assert run.final_score.value >= config.SCORE_THRESHOLD

    # terminated cleanly with COMPLETE
    assert run.stop_code is StopCode.COMPLETE

    # evaluator-mediated Decision Reports landed in memory (sole writer = evaluator)
    assert len(mem.all_reports()) > 0
    assert run.reports and len(run.reports) == len(mem.all_reports())

    # every component participated in the audit substrate
    components = {r.component for r in mem.all_reports()}
    assert {"triage", "seeder", "evaluator"} <= components
