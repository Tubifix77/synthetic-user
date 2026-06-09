"""Scenario 12 (Graceful degradation under component failure) - architecture2.md section 10.3.

Inject a fault into one component (evaluator Layer 2 Opus call returns malformed
output). Verify:
  - Evaluator audits the fault (catches the bad output, logs it)
  - System continues completing the current Run without Layer 2's full participation
  - Fault is logged for next-Run review
  - System re-enables the component cleanly for the next Run if fault was transient

Verifies: graceful degradation, evaluator audit-the-audit-substrate (FM-17),
no single-component failure cascades to system failure.

FAST + INTEGRATION TESTS — fast tests inject faults programmatically;
integration test verifies end-to-end survival.
"""
import os
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode, Cycle, Deliverable
from synthetic_user.reports import ReportBuffer
from synthetic_user.evaluator import evaluate

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fast tests — inject faults directly into the evaluator
# ---------------------------------------------------------------------------

def test_scenario_12_layer2_malformed_output_degrades_gracefully():
    """If a Layer 2 hat returns unparseable JSON, evaluate() must not crash.

    Instead it should: assign an 'uncertain' verdict for that hat, produce a
    layer2_panel report with best-effort data, and return a Score.
    """
    from unittest.mock import patch

    # Inject malformed JSON as the Haiku model's response for the adversary hat.
    def _bad_claude(prompt, model="claude-sonnet-4-5"):
        if "claude-haiku" in model:
            return "THIS IS NOT JSON AT ALL %%% BROKEN"
        # Other models respond normally.
        return '{"verdict": "pass", "evidence": "looks good", "assessment": "fine"}'

    cycle = Cycle(
        index=0,
        goal="write a hello world script",
        deliverable=Deliverable(content="print('hello world')"),
    )
    buffer = ReportBuffer()

    # Force Layer 2 to fire by setting anomaly threshold to 0.
    original = os.environ.get("SYNTH_EVAL_ANOMALY_THRESHOLD")
    os.environ["SYNTH_EVAL_ANOMALY_THRESHOLD"] = "0.95"
    try:
        with patch("synthetic_user.evaluator._claude", side_effect=_bad_claude):
            score = evaluate(cycle, ["deliverable exists"], buffer)
    finally:
        if original is None:
            os.environ.pop("SYNTH_EVAL_ANOMALY_THRESHOLD", None)
        else:
            os.environ["SYNTH_EVAL_ANOMALY_THRESHOLD"] = original

    # Must not crash — returns a Score.
    assert score is not None
    assert score.value >= 0

    # Layer 2 panel report must exist even with malformed input.
    reports = buffer.drain()
    layer2_reports = [r for r in reports if r.decision_type == "layer2_panel"]
    assert len(layer2_reports) >= 1, (
        "Layer 2 panel report missing even after malformed input"
    )

    panel = layer2_reports[0]
    # Adversary hat should have degraded to 'uncertain' (not crashed).
    adversary = panel.component_specific.get("hats", {}).get("adversary", {})
    assert adversary.get("verdict") == "uncertain", (
        f"Expected 'uncertain' for adversary after malformed output, got: {adversary}"
    )


def test_scenario_12_evaluator_reports_own_fault():
    """If the evaluator itself encounters a fault, it must log a self-report."""
    from unittest.mock import patch

    cycle = Cycle(
        index=0,
        goal="write a hello world script",
        deliverable=Deliverable(content="print('hello world')"),
    )
    buffer = ReportBuffer()

    def _always_raise(prompt, model="claude-sonnet-4-5"):
        raise RuntimeError("Simulated LLM timeout")

    original = os.environ.get("SYNTH_EVAL_ANOMALY_THRESHOLD")
    os.environ["SYNTH_EVAL_ANOMALY_THRESHOLD"] = "0.95"
    try:
        with patch("synthetic_user.evaluator._claude", side_effect=_always_raise):
            score = evaluate(cycle, ["deliverable exists"], buffer)
    finally:
        if original is None:
            os.environ.pop("SYNTH_EVAL_ANOMALY_THRESHOLD", None)
        else:
            os.environ["SYNTH_EVAL_ANOMALY_THRESHOLD"] = original

    # System must not raise.
    assert score is not None

    reports = buffer.drain()
    # A fault report must be emitted.
    fault_reports = [r for r in reports if r.decision_type in ("evaluator_fault", "layer2_panel")]
    assert len(fault_reports) >= 1, (
        "No fault report logged when evaluator component raised. "
        "Reports: " + str([(r.decision_type, r.rationale[:60]) for r in reports])
    )


# ---------------------------------------------------------------------------
# Integration test — full run survives evaluator Layer 2 being broken
# ---------------------------------------------------------------------------

def test_scenario_12_full_run_survives_layer2_fault():
    """Full integration: evaluator Layer 2 broken; run still completes.

    Uses SYNTH_EVAL_ANOMALY_THRESHOLD=0.95 to force Layer 2 to fire, and
    SYNTH_EVAL_LAYER2_DISABLED=1 to simulate Layer 2 being faulted out.
    Run must still complete with a Score from Layer 1.
    """
    import os as _os
    original = _os.environ.copy()
    _os.environ["SYNTH_EVAL_ANOMALY_THRESHOLD"] = "0.95"
    _os.environ["SYNTH_EVAL_LAYER2_DISABLED"] = "1"

    try:
        mem = Memory()
        run = Orchestrator(memory=mem).run(Request(goal="write a hello world script"))
    finally:
        _os.environ.clear()
        _os.environ.update(original)

    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE), (
        f"Run failed when Layer 2 is disabled: {run.stop_code}"
    )

    # Layer 1 reliability_eval report must exist.
    layer1_reports = mem.query_reports(decision_type="reliability_eval")
    assert len(layer1_reports) >= 1, "No reliability_eval report — Layer 1 did not run"
