"""Orchestrator (architecture2.md section 2.9). Walking-skeleton: drives one Run
end-to-end through stub components. Thin by design; owns state and the report buffer.

Real version spawns/maintains Claude Code sessions; here the executor is stubbed.
"""
from __future__ import annotations
from synthetic_user import config, triage as triage_mod, seeder, executor, evaluator
from synthetic_user.types import Request, Route, Run, Cycle
from synthetic_user.reports import ReportBuffer
from synthetic_user.memory import Memory


class Orchestrator:
    def __init__(self, memory: Memory, config=config) -> None:
        self.memory = memory
        self.config = config

    def run(self, request: Request) -> Run:
        buffer = ReportBuffer()
        route = triage_mod.triage(request, buffer)
        run = Run(request=request, route=route)

        if route is not Route.LOOP:
            run.rejected_reason = "triage did not route to loop"
            evaluator.ingest_reports(buffer, self.memory)
            run.reports = self.memory.all_reports()
            return run

        # cycle 0: cold-start pass-through
        goal = seeder.cold_start(request.goal, buffer)
        criteria = ["deliverable exists"]  # cycle-0 criteria (real: CC done-when declaration)

        for i in range(self.config.MAX_CYCLES_PER_RUN):
            cycle = Cycle(index=i, goal=goal)
            cycle.deliverable = executor.execute(goal)
            cycle.score = evaluator.evaluate(cycle, criteria, buffer)
            run.cycles.append(cycle)

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
