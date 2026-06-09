"""Scenario 9 (Decision Reports queryable end-to-end) - architecture2.md section 10.3.

Run a representative scenario. Query the report store afterwards with various
filters. Verify returned reports match runtime decisions, schema-validate, and
are correctly flagged.

Verifies: report buffer flow, evaluator schema validation, query interface,
schema completeness (all required fields present on every report).

FAST TEST — uses stub executor; no LLM call needed.
"""
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request
from synthetic_user.reports import DecisionReport


_REQUIRED_FIELDS = {
    "component", "decision_type", "selected", "rationale",
    "report_id", "confidence", "reversibility",
}


def _assert_schema_complete(report: DecisionReport) -> None:
    for field in _REQUIRED_FIELDS:
        val = getattr(report, field, None)
        assert val is not None and val != "", (
            f"Report {report.report_id} from {report.component} missing required "
            f"field '{field}'. Got: {val!r}"
        )


def test_scenario_09_reports_queryable_by_component():
    mem = Memory()
    Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    # Query by component — triage, seeder, evaluator should all have entries.
    for component in ("triage", "seeder", "evaluator"):
        results = mem.query_reports(component=component)
        assert len(results) >= 1, f"No reports found for component={component!r}"
        for r in results:
            assert r.component == component

    # Non-existent component returns empty list, not an error.
    assert mem.query_reports(component="nonexistent") == []


def test_scenario_09_reports_queryable_by_decision_type():
    mem = Memory()
    Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    cold_starts = mem.query_reports(decision_type="cold_start")
    assert len(cold_starts) >= 1
    for r in cold_starts:
        assert r.decision_type == "cold_start"

    evals = mem.query_reports(decision_type="reliability_eval")
    assert len(evals) >= 1


def test_scenario_09_reports_queryable_combined_filters():
    mem = Memory()
    Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    # Filtering by both component and decision_type should narrow correctly.
    results = mem.query_reports(component="seeder", decision_type="multi_lens_reflect")
    assert len(results) >= 1
    for r in results:
        assert r.component == "seeder"
        assert r.decision_type == "multi_lens_reflect"

    # Impossible combination returns empty.
    empty = mem.query_reports(component="triage", decision_type="multi_lens_reflect")
    assert empty == []


def test_scenario_09_all_reports_schema_complete():
    """Every report in the store must satisfy the required-field schema."""
    mem = Memory()
    Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    all_reports = mem.all_reports()
    assert len(all_reports) >= 3  # triage + seeder + evaluator minimum

    for report in all_reports:
        _assert_schema_complete(report)


def test_scenario_09_reports_with_audit_flags():
    """Reports emitted with audit_flags are queryable by flag."""
    mem = Memory()
    Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    # No reports have audit flags in the walking-skeleton run — query returns empty.
    flagged = mem.query_reports(has_flag="triple_check_fired")
    assert isinstance(flagged, list)  # returns list, not error

    # Seed a report with a flag directly and verify query finds it.
    from synthetic_user.reports import DecisionReport
    flagged_report = DecisionReport(
        component="brain", decision_type="dispatch",
        selected="proceed", rationale="test",
        audit_flags=["triple_check_fired"],
    )
    mem.write_reports([flagged_report])
    results = mem.query_reports(has_flag="triple_check_fired")
    assert len(results) == 1
    assert results[0].report_id == flagged_report.report_id
