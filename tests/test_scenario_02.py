"""Scenario 2 (Refinement Run) - architecture2.md section 10.3.

Cold-start request requires multi-step work ("build CSV deduplicator").
Cycle 0 builds. Seeder reflects: production+skeptical lenses surface untested
edge cases, returns a refinement direction. Cycle 1 refines. Seeder reflects
again: skeptical lens dominates, stops with REFINEMENT_COMPLETE.

Verifies: multi-cycle Runs, seeder multi-lens reflection, cycle preparation
between cycles, REFINEMENT_COMPLETE terminal code.
"""
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode


def test_scenario_02_refinement_run():
    mem = Memory()
    run = Orchestrator(memory=mem).run(Request(goal="build a CSV deduplicator"))

    # multi-cycle: at least cycle 0 (build) + cycle 1 (refinement)
    assert len(run.cycles) >= 2

    # the seeder changed direction between cycles (cycle prep happened)
    assert run.cycles[0].goal != run.cycles[1].goal

    # final cycle still produced a deliverable
    assert run.deliverable is not None and run.deliverable.content

    # evaluator scored the final cycle above threshold
    assert run.final_score is not None and run.final_score.passed

    # terminated with the refinement-specific terminal code, not COMPLETE
    assert run.stop_code is StopCode.REFINEMENT_COMPLETE

    # all three core components left Decision Reports
    components = {r.component for r in mem.all_reports()}
    assert {"triage", "seeder", "evaluator"} <= components

    # seeder must have emitted a "lenses" report during cycle-0 reflection
    seeder_reports = [r for r in mem.all_reports() if r.component == "seeder"]
    lens_reports = [r for r in seeder_reports if r.decision_type == "multi_lens_reflect"]
    assert len(lens_reports) >= 1, "seeder multi-lens reflection not recorded"
