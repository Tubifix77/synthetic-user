"""Executor = the framework (Claude Code). architecture2.md section 2.2.

WALKING-SKELETON STUB: returns a canned deliverable so the loop can be tested
end-to-end WITHOUT invoking a model. Scenario 1 verifies plumbing, not behaviour.
Real version (scenarios 3+) drives the main Claude Code thread via `claude -p`;
this is the ONLY component that is legitimately stubbed for scenario 1.
"""
from __future__ import annotations
from synthetic_user.types import Deliverable


def execute(prompt: str) -> Deliverable:
    return Deliverable(
        content=f"[stub deliverable for goal: {prompt[:80]}]",
        artifacts={"stub": True, "prompt_len": len(prompt)},
    )
