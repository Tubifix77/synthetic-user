"""Drive a real Run for a human front end (CLI / web UI) and keep a record of it.

A Run started here uses the real executor (`claude -p`), runs in a background
thread, and writes `run_state/<run-id>/run.json` as it goes — the same folder
the hooks write `hooks_log.jsonl` into. Only one Run at a time: the framework
works in this repo, so two concurrent Runs would edit the same files.

Nothing here changes how a Run behaves; it composes Orchestrator + executor the
way OPERATIONS.md §6 does and observes the result.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from synthetic_user import config
from synthetic_user.executor import PROJECT_ROOT, ClaudeCodeExecutor, summarize_run_cost
from synthetic_user.memory import Memory
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.types import Request, Route

RUNS_DIR = PROJECT_ROOT / "run_state"
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
_CACHE_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".mypy_cache"}

_lock = threading.Lock()
_active: "RunSession | None" = None


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:6]
    return "-".join(words) or "run"


def _git_status() -> set[str]:
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT), timeout=30,
                           stdin=subprocess.DEVNULL)
        return {line[3:].strip() for line in r.stdout.splitlines() if line.strip()}
    except Exception:  # noqa: BLE001
        return set()


class RunSession:
    def __init__(self, goal: str, models: dict[str, str] | None = None, use_workspace: bool = True,
                 allow_tests: bool = False):
        self.goal = goal.strip()
        self.models = {role: tier for role, tier in (models or {}).items() if role in config.MODEL_TIERS and tier}
        # Per-Run settings travel as env vars: the executor, hooks and director command all inherit them.
        self.env = {f"SYNTH_MODEL_{role.upper()}": tier for role, tier in self.models.items()}
        if allow_tests:
            self.env["SYNTH_ALLOW_TESTS"] = "1"
        self.executor = ClaudeCodeExecutor()
        self.dir: Path = self.executor.state_dir
        self.id = self.dir.name
        self.workspace = (WORKSPACE_DIR / f"{time.strftime('%Y%m%d-%H%M')}-{_slug(self.goal)}"
                          if use_workspace else None)
        self.record: dict[str, Any] = {
            "id": self.id,
            "goal": self.goal,
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "workspace": self.workspace.relative_to(PROJECT_ROOT).as_posix() if self.workspace else None,
            "allow_tests": allow_tests,
            "models": {},
            "progress": [],
            "triage": None,
            "cycles": [],
            "stop_code": None,
            "reports": [],
            "files_changed": [],
            "cost": None,
            "error": None,
        }
        self._thread: threading.Thread | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────
    def start(self) -> None:
        self._thread = threading.Thread(target=self._work, name=f"run-{self.id}", daemon=True)
        self._thread.start()

    def wait(self) -> None:
        if self._thread:
            self._thread.join()

    def _save(self) -> None:
        tmp = self.dir / "run.json.tmp"
        tmp.write_text(json.dumps(self.record, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.dir / "run.json")

    def _on_event(self, kind: str, data: dict) -> None:
        self.record["progress"].append({"ts": time.time(), "kind": kind, **data})
        if kind == "triage":
            self.record["triage"] = data
        self._save()

    def _execute(self, goal: str):
        prompt = goal
        if self.workspace is not None:
            self.workspace.mkdir(parents=True, exist_ok=True)
            rel = self.workspace.relative_to(PROJECT_ROOT).as_posix()
            prompt = (f"Work inside the folder {rel}/ — create every file for this task there.\n\n{goal}")
        return self.executor.execute(prompt)

    def _work(self) -> None:
        global _active
        saved_env = {k: os.environ.get(k) for k in self.env}
        try:
            os.environ.update(self.env)
            self.record["models"] = {role: config.model_for(role) for role in config.MODEL_TIERS}
            before = _git_status()
            self._save()

            memory = Memory()
            run = Orchestrator(memory=memory, executor_fn=self._execute, on_event=self._on_event).run(
                Request(goal=self.goal))

            changed = _git_status() - before
            if self.workspace is not None and self.workspace.exists():  # workspace/ is gitignored
                changed |= {f.relative_to(PROJECT_ROOT).as_posix() for f in self.workspace.rglob("*")
                            if f.is_file() and not _CACHE_DIRS & set(f.relative_to(self.workspace).parts)}
            self.record["files_changed"] = sorted(changed)
            self.record["cycles"] = [{
                "index": c.index,
                "goal": c.goal,
                "score": c.score.value if c.score else None,
                "passed": c.score.passed if c.score else None,
                "deliverable": c.deliverable.content if c.deliverable else "",
                "turns": (c.deliverable.artifacts or {}).get("num_turns") if c.deliverable else None,
            } for c in run.cycles]
            self.record["cost"] = summarize_run_cost([c.deliverable for c in run.cycles if c.deliverable])
            self.record["stop_code"] = run.stop_code.value if run.stop_code else None
            self.record["reports"] = [{
                "component": r.component, "decision_type": r.decision_type, "selected": r.selected,
                "rationale": r.rationale, "confidence": r.confidence, "audit_flags": r.audit_flags,
            } for r in run.reports]
            self.record["status"] = "rejected" if run.route is Route.REJECT else "complete"
            if run.route is Route.REJECT:
                self.record["error"] = run.rejected_reason
        except Exception as exc:  # noqa: BLE001
            self.record["status"] = "error"
            self.record["error"] = f"{exc}\n\n{traceback.format_exc()[-1500:]}"
        finally:
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            self.record["finished_at"] = time.time()
            self._save()
            with _lock:
                if _active is self:
                    _active = None


# ── public API ──────────────────────────────────────────────────────────────

def start_run(goal: str, models: dict[str, str] | None = None, use_workspace: bool = True,
              allow_tests: bool = False) -> RunSession:
    """Start a Run in the background. Raises RuntimeError if one is already running."""
    global _active
    if not goal or not goal.strip():
        raise ValueError("Describe what you want built first.")
    with _lock:
        if _active is not None:
            raise RuntimeError("A Run is already in progress — wait for it to finish.")
        session = RunSession(goal, models, use_workspace, allow_tests)
        _active = session
    session.start()
    return session


def active_run_id() -> str | None:
    return _active.id if _active else None


def load_run(run_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        return None
    path = RUNS_DIR / run_id / "run.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    from hooks.state import read_hooks_log
    record["hook_events"] = read_hooks_log(RUNS_DIR / run_id)
    return record


def list_runs(limit: int = 50) -> list[dict]:
    """Runs started from the CLI/UI, newest first (test-suite state dirs have no run.json)."""
    rows = []
    for path in RUNS_DIR.glob("*/run.json"):
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        rows.append({k: r.get(k) for k in ("id", "goal", "status", "started_at", "finished_at", "stop_code")})
    rows.sort(key=lambda r: r.get("started_at") or 0, reverse=True)
    return rows[:limit]
