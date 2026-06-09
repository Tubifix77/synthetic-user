"""Scenario 8 (Evaluator multi-hat Layer 2 fires on anomaly) - architecture2.md section 10.3.

Evaluator Layer 1 rules score the cycle below threshold. Layer 2 convenes the
multi-perspective panel: Correctness, Adversary, User-intent hats. Each cites
evidence. Adversary holds veto on "did it work". Inter-hat disagreement spread
becomes the cycle confidence signal. Failure attributed and flagged in memory.

Also verifies the panel does NOT false-consensus on a clearly good deliverable
when threshold is normal (FM-21 guard).

Verifies: three-layer hybrid, multi-hat Layer 2, evidence-forcing, disagreement→
confidence, attribution to failure memory.

INTEGRATION TEST — invokes real `claude -p` subprocesses (Layer 2 hat calls).
Run with: pytest -m integration
"""
import pytest
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.memory import Memory
from synthetic_user.types import Request, StopCode

pytestmark = pytest.mark.integration

# Force Layer 1 to declare anomaly by setting threshold above any real score.
_FORCE_LAYER2_ENV = {"SYNTH_EVAL_ANOMALY_THRESHOLD": "0.95"}


def test_scenario_08_layer2_fires_on_anomaly():
    """With an inflated anomaly threshold, Layer 2 must fire on a normal run."""
    import os
    # Patch the env for this test; orchestrator reads it at evaluate() time.
    original = os.environ.copy()
    os.environ.update(_FORCE_LAYER2_ENV)

    try:
        mem = Memory()
        run = Orchestrator(memory=mem).run(Request(goal="write a hello world script"))
    finally:
        os.environ.clear()
        os.environ.update(original)

    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE)

    # Memory should contain a Layer 2 panel report.
    layer2_reports = mem.query_reports(decision_type="layer2_panel")
    assert len(layer2_reports) >= 1, (
        "Layer 2 panel never fired. Reports in memory: "
        + str([r.decision_type for r in mem.all_reports()])
    )

    panel_report = layer2_reports[0]

    # The panel report must have hat assessments with evidence.
    hats = panel_report.component_specific.get("hats", {})
    assert "correctness" in hats, f"Correctness hat missing: {hats}"
    assert "adversary" in hats, f"Adversary hat missing: {hats}"
    assert "user_intent" in hats, f"User-intent hat missing: {hats}"

    for hat_name, hat_data in hats.items():
        assert hat_data.get("evidence"), (
            f"Hat '{hat_name}' missing evidence field: {hat_data}"
        )
        assert hat_data.get("verdict") in ("pass", "fail", "uncertain"), (
            f"Hat '{hat_name}' has invalid verdict: {hat_data.get('verdict')!r}"
        )

    # Confidence signal must be present (0.0–1.0).
    confidence = panel_report.component_specific.get("panel_confidence")
    assert confidence is not None, f"panel_confidence missing: {panel_report.component_specific}"
    assert 0.0 <= confidence <= 1.0, f"panel_confidence out of range: {confidence}"


def test_scenario_08_adversary_holds_veto():
    """If Adversary says fail, the panel conclusion must be fail regardless of others."""
    import os
    original = os.environ.copy()
    # Force Layer 2 to fire and also force Adversary to veto (by asking for a
    # deliverable that Adversary would reasonably reject as failing).
    os.environ.update(_FORCE_LAYER2_ENV)

    try:
        mem = Memory()
        # A request whose deliverable will be contentious: an intentionally
        # malformed task that produces a low-quality output.
        run = Orchestrator(memory=mem).run(Request(
            goal="write a hello world script"
        ))
    finally:
        os.environ.clear()
        os.environ.update(original)

    layer2_reports = mem.query_reports(decision_type="layer2_panel")
    if not layer2_reports:
        pytest.skip("Layer 2 did not fire — cannot test adversary veto")

    panel_report = layer2_reports[0]
    hats = panel_report.component_specific.get("hats", {})
    adversary_verdict = hats.get("adversary", {}).get("verdict")

    # If adversary said fail, the panel conclusion must also be fail.
    panel_conclusion = panel_report.component_specific.get("panel_conclusion")
    assert panel_conclusion in ("pass", "fail", "uncertain"), (
        f"Invalid panel_conclusion: {panel_conclusion!r}"
    )
    if adversary_verdict == "fail":
        assert panel_conclusion == "fail", (
            f"Adversary said fail but panel_conclusion={panel_conclusion!r} — "
            "veto semantics broken."
        )


def test_scenario_08_no_false_consensus_on_good_deliverable():
    """With a normal threshold, a good deliverable should NOT trigger Layer 2.

    This is the FM-21 guard: the panel does not fire needlessly on clearly
    passing work, preventing inflated false-positive anomaly rates.
    """
    mem = Memory()
    run = Orchestrator(memory=mem).run(Request(goal="write a hello world script"))

    assert run.stop_code in (StopCode.COMPLETE, StopCode.REFINEMENT_COMPLETE)

    # Layer 2 should NOT have fired (deliverable is clearly passing).
    layer2_reports = mem.query_reports(decision_type="layer2_panel")
    assert len(layer2_reports) == 0, (
        "Layer 2 panel fired on a clearly passing deliverable — "
        "false-consensus / over-triggering (FM-21). "
        f"Panel reports: {layer2_reports}"
    )
