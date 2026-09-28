"""Orchestrator (architecture2.md section 2.9). Drives one Run end-to-end:
triage → seeder → execute → evaluate → reflect. Thin by design; owns state and
the report buffer.

The default executor is the instant stub (fast scenarios). A real Run injects
`ClaudeCodeExecutor().execute` as executor_fn — synthetic_user.runner does this
for the CLI and the web UI.
"""
from __future__ import annotations
from typing import Any, Callable
from synthetic_user import config, triage as triage_mod, seeder, executor, evaluator
from synthetic_user.types import Deliverable, Request, Route, Run, Cycle
from synthetic_user.reports import ReportBuffer
from synthetic_user.memory import Memory

EventFn = Callable[[str, dict[str, Any]], None]


class Orchestrator:
    def __init__(
        self,
        memory: Memory,
        config=config,
        executor_fn: Callable[[str], Deliverable] | None = None,
        on_event: EventFn | None = None,
    ) -> None:
        self.memory = memory
        self.config = config
        self._execute = executor_fn or executor.execute
        self._on_event = on_event

    def _emit(self, kind: str, **data: Any) -> None:
        """Progress notification for observers (CLI/UI). Never affects the Run."""
        if self._on_event is not None:
            try:
                self._on_event(kind, data)
            except Exception:  # noqa: BLE001
                pass

    def run(self, request: Request) -> Run:
        buffer = ReportBuffer()
        route, rejected_reason = triage_mod.triage(request, buffer)
        run = Run(request=request, route=route, rejected_reason=rejected_reason)
        self._emit("triage", route=route.value, reason=rejected_reason)

        if route is not Route.LOOP:
            evaluator.ingest_reports(buffer, self.memory)
            run.reports = self.memory.all_reports()
            return run

        # cycle 0: cold-start pass-through
        goal = seeder.cold_start(request.goal, buffer)
        criteria = ["deliverable exists"]  # cycle-0 criteria (real: CC done-when declaration)

        for i in range(self.config.MAX_CYCLES_PER_RUN):
            cycle = Cycle(index=i, goal=goal)
            self._emit("cycle_start", index=i, goal=goal)
            cycle.deliverable = self._execute(goal)
            cycle.score = evaluator.evaluate(cycle, criteria, buffer)
            run.cycles.append(cycle)
            self._emit("cycle_end", index=i, score=cycle.score.value, passed=cycle.score.passed)

            # evaluator drains the report buffer to memory at cycle close (sole writer)
            evaluator.ingest_reports(buffer, self.memory)

            decision = seeder.reflect(cycle, run, buffer)
            evaluator.ingest_reports(buffer, self.memory)  # persist the reflect report too
            if decision.stop is not None:
                run.stop_code = decision.stop
                break
            goal = decision.direction or goal
            criteria = decision.criteria or criteria

        run.reports = self.memory.all_reports()
        return run
