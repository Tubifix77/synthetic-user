"""Executor = the framework (Claude Code). architecture2.md section 2.2.

Two implementations:
  - execute()           — stub used by scenarios 1/2/15 (no subprocess, instant)
  - ClaudeCodeExecutor  — real impl used by scenarios 3+; drives `claude -p`

The real executor maintains session_id across cycles so subsequent cycle prompts
resume the same CC session (one Run = one CC session, section 2.9).
"""
from __future__ import annotations
import json
import os
import subprocess
import uuid
from pathlib import Path
from synthetic_user.types import Deliverable
from synthetic_user.utils import retry_with_backoff

PROJECT_ROOT = Path(__file__).parent.parent
_CC_TIMEOUT = 600  # seconds; triple-check adds ~3 × 30s of nested LLM calls


# ---------------------------------------------------------------------------
# Stub (scenarios 1 / 2 / 15)
# ---------------------------------------------------------------------------

def execute(prompt: str) -> Deliverable:
    return Deliverable(
        content=f"[stub deliverable for goal: {prompt[:80]}]",
        artifacts={"stub": True, "prompt_len": len(prompt)},
    )


# ---------------------------------------------------------------------------
# Real executor (scenarios 3+)
# ---------------------------------------------------------------------------

class ClaudeCodeExecutor:
    """Drives `claude -p` for one Run.  One instance per Run; reuse across cycles."""

    def __init__(
        self,
        project_root: Path | None = None,
        extra_flags: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ):
        self.project_root = project_root or PROJECT_ROOT
        self.extra_flags = extra_flags or []
        self.extra_env = extra_env or {}
        self.session_id: str | None = None
        self._state_dir: Path | None = None

    @property
    def state_dir(self) -> Path:
        """Per-session state directory for hook handler IPC."""
        if self._state_dir is None:
            run_id = self.session_id or uuid.uuid4().hex
            self._state_dir = self.project_root / "run_state" / run_id
            self._state_dir.mkdir(parents=True, exist_ok=True)
        return self._state_dir

    def execute(self, goal: str) -> Deliverable:
        """Run one CC turn with the given goal. Resumes the same session if called again."""
        cmd = [
            "claude", "-p", goal,
            "--output-format", "json",
            "--dangerously-skip-permissions",
        ] + self.extra_flags

        if self.session_id:
            cmd += ["--resume", self.session_id]

        env = {**os.environ, "SYNTH_SESSION_DIR": str(self.state_dir), **self.extra_env}

        def _run_once() -> dict:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.project_root),
                env=env,
                timeout=_CC_TIMEOUT,
            )
            if r.returncode != 0:
                raise RuntimeError(
                    f"claude -p failed (exit {r.returncode}): {r.stderr[:500]}"
                )
            try:
                out = json.loads(r.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"claude -p output was not valid JSON: {r.stdout[:200]}"
                ) from exc
            if out.get("is_error"):
                raise RuntimeError(f"claude -p returned an error result: {out}")
            return out

        output = retry_with_backoff(_run_once)

        # Persist the session_id so the next cycle resumes the same session.
        # NOTE: _state_dir is NOT updated here — hooks already wrote to the UUID path
        # and we must keep reading from that same directory throughout the Run.
        if "session_id" in output:
            self.session_id = output["session_id"]

        content = output.get("result") or ""
        return Deliverable(
            content=content,
            artifacts={
                "session_id": self.session_id,
                "num_turns": output.get("num_turns", 1),
                "cost_usd": output.get("total_cost_usd"),
            },
        )

    def hooks_log(self) -> list[dict]:
        """Return all hook events logged during this Run's CC session."""
        from hooks.state import read_hooks_log
        return read_hooks_log(self.state_dir)


def summarize_run_cost(deliverables: list[Deliverable]) -> dict:
    """Aggregate cost and turn counts across all cycles of a Run.

    Returns a dict with total_cost_usd, total_turns, and cycle_count so
    callers can log or gate on spend without repeating the accumulation logic.
    """
    total_cost = 0.0
    total_turns = 0
    for d in deliverables:
        cost = d.artifacts.get("cost_usd")
        if cost is not None:
            total_cost += float(cost)
        turns = d.artifacts.get("num_turns")
        if turns is not None:
            total_turns += int(turns)
    return {
        "total_cost_usd": round(total_cost, 6),
        "total_turns": total_turns,
        "cycle_count": len(deliverables),
    }
