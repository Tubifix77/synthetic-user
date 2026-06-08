"""Scenario 15 (Seeder validation gate) - architecture2.md section 10.3.

Compares seeder cycle-boundary decisions against pre-recorded human verdicts on a
fixed sample. A low agreement rate signals the seeder needs replacing, not tuning.

Human judgments are recorded in tests/fixtures/scenario_15_human_verdicts.json.
The test is fully deterministic and CI-safe — human votes were supplied once by
hand; they do not change between runs.

Verifies: seeder grounding quality, highest-risk component fitness, the
synthetic-oversight thesis at its weakest point (architecture2.md section 2.1).
"""
from __future__ import annotations
import json
from pathlib import Path

from synthetic_user import seeder as seeder_mod
from synthetic_user.reports import ReportBuffer
from synthetic_user.types import Cycle, Deliverable, Request, Run, Route, Score, StopCode

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scenario_15_human_verdicts.json"
AGREEMENT_THRESHOLD = 0.70  # below this → seeder needs replacing, not tuning


def _decision_to_verdict(decision) -> str:
    """Map a SeederDecision to the same vocabulary as the fixture human_verdict field."""
    if decision.stop is StopCode.COMPLETE:
        return "complete"
    if decision.stop is StopCode.REFINEMENT_COMPLETE:
        return "refinement_complete"
    return "continue"


def _build_cycle_and_run(fixture: dict) -> tuple[Cycle, Run]:
    cycle = Cycle(
        index=fixture["cycle_index"],
        goal=fixture["request_goal"],
        deliverable=Deliverable(content=fixture["deliverable_content"]),
        score=Score(
            value=fixture["score_value"],
            passed=fixture["score_passed"],
            criteria_met={"deliverable exists": fixture["score_passed"]},
        ),
    )
    run = Run(
        request=Request(goal=fixture["request_goal"]),
        route=Route.LOOP,
        cycles=[cycle],
    )
    return cycle, run


def test_scenario_15_seeder_matches_human_judgment():
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(fixtures) >= 5, "need at least 5 samples for a meaningful agreement rate"

    agreements = []
    mismatches = []

    for fx in fixtures:
        cycle, run = _build_cycle_and_run(fx)
        buffer = ReportBuffer()
        decision = seeder_mod.reflect(cycle, run, buffer)
        seeder_verdict = _decision_to_verdict(decision)
        agreed = seeder_verdict == fx["human_verdict"]
        agreements.append(agreed)
        if not agreed:
            mismatches.append({
                "id": fx["id"],
                "description": fx["description"],
                "human": fx["human_verdict"],
                "seeder": seeder_verdict,
            })

    rate = sum(agreements) / len(agreements)

    # Print detail so a failing run is immediately actionable.
    if mismatches:
        print(f"\nSeeder/human mismatches ({len(mismatches)}/{len(fixtures)}):")
        for m in mismatches:
            print(f"  [{m['id']}] {m['description']}")
            print(f"    human={m['human']}  seeder={m['seeder']}")

    assert rate >= AGREEMENT_THRESHOLD, (
        f"Seeder agreement rate {rate:.0%} < {AGREEMENT_THRESHOLD:.0%} threshold — "
        f"seeder needs replacing, not tuning (architecture2.md section 2.1)."
    )
