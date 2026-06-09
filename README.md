# Synthetic User

> A closed-loop control system that wraps an existing agentic framework (Claude Code as v1 reference) with infrastructure replacing the human roles that ordinarily sit around such a loop.

**Status: BUILT — first full pass complete.** All fifteen acceptance scenarios pass against a live Claude Code subprocess. The design phase (v1.5) is locked in [architecture2.md](architecture2.md); the implemented system is described in [architecture2.md section 12](architecture2.md#12-build-status--what-was-actually-implemented) and the [operations manual](OPERATIONS.md).

## What it is

Agentic frameworks like Claude Code do real work, but a human still has to drive them from outside: triaging incoming requests, deciding what to work on, watching and answering questions, managing context, and reviewing afterward. Synthetic User replaces that human layer with a structured set of components, each with bounded authority, all bound by reality through the framework's real tool calls.

The system replaces six distinct human roles around an agentic framework:

- **Triage gate** — routes incoming requests (loop / direct-handle / reject)
- **Seeder** — cycle-boundary multi-lens reflection + cycle preparation
- **Steering brain** — in-flight resolution of framework doubts and action patterns (the `consult_director` path)
- **Context steward** — continuous context monitoring during execution
- **Evaluator** — post-hoc learning, schema validation, audit trail, multi-hat reliability panel
- **Decision Reports** — structured reasoning audit substrate across all components

The agentic loop itself — planning, tool use, code generation, verification — is **inherited from the framework** (Claude Code in v1). Synthetic User does not reinvent agentic loops; it wraps existing ones.

## What it isn't

**Not an attempt to remove humans from agentic systems.** The system replaces specific cognitive roles around the loop, not the human as beneficiary of the work.

**Not an alignment experiment.** Components optimize reliability and audit trail, not morality. "Did this work?" not "was this good?"

**Not AGI.** It is a self-updating control system around an existing framework. That is interesting on its own terms.

**Not a continuation of [Growing Spine](https://github.com/Tubifix77/growing-spine).** Same era, same author, related lineage, different hypothesis. Growing Spine is a creature with one constraint and no enforcement layer. Synthetic User is a closed loop with explicit roles, schemas, and audit substrate.

## How it actually attaches to Claude Code

The wrapper drives the official `claude` CLI headlessly (`claude -p`) and intercepts the framework through two mechanisms it already exposes:

- **Hooks** (`.claude/settings.json`) — `SessionStart` injects operating instructions, `Stop` runs the halt-language router (reactive steering), `PreToolUse` and `PostToolUse` feed the steward and action-pattern triggers.
- **An MCP tool** (`.mcp.json` → `director_mcp/`) — `consult_director` is the proactive steering path: the framework calls it instead of stopping to ask, the brain answers, the framework continues without ever halting.

These two paths cover uncorrelated failure modes — if the framework forgets to consult, the Stop hook still catches halt-language; if halt-language is ambiguous, the consult path still works. Both were verified end-to-end (scenarios 3 and 4).

## The hypothesis being tested

Two LLMs talking to each other almost always collapse into a closed epistemic loop: internally coherent, externally wrong. The standard objection to multi-agent self-play is that it generates plausible nonsense at scale.

The claim this project tests: **a closed loop becomes stable when external reality is allowed to disagree with it often enough, AND when each component's reasoning is documented in a form a human can audit without replaying the system.**

Concretely — given triage + seeder + brain + steward + evaluator + real tool execution + persistent memory + Decision Reports, can the system improve at a non-trivial task over time without drifting into reward-hacking, hallucination ecosystems, or goal collapse?

If yes: this is a viable training-data-free agent improvement pattern.
If no: the failure modes themselves are the contribution — they map the boundary between useful self-play and pure self-talk.

## Architecture

The buildable architecture lives in [architecture2.md](architecture2.md) (v1.5, locked). Fifteen revisions across the design phase: v0.1 (initial five-component decomposition) → v0.9 (context steward + cycle preparation) → v1.0 (CC hook binding + hybrid synth-user dispatch) → v1.1 (Decision Reports as audit substrate) → v1.2 (acceptance-test-driven implementation strategy + all TBDs resolved) → v1.3 (pre-build audit: dispatch re-grounded on the consult_director MCP tool, integration surface specified, 8 holes closed) → v1.4 (current-science audit: autonomy edge, seeder hardening, Decision Reports as coordination backbone, steward degradation proxy) → v1.5 (multi-perspective evaluator: Layer 2 becomes a panel of perspective hats, resolving the validate-the-validator problem and supplying the autonomy dial's confidence signal).

**Key concepts:**

- **Run** — one bounded Synthetic User goal-pursuit, made of one or more cycles, terminates on a seeder stop code
- **Cycle** — one seeder → framework execution → evaluator scoring iteration; maps 1:1 to a Claude Code "turn"
- **Hybrid synth-user dispatch** — proactive entry via the `consult_director` MCP tool + reactive entry via the `Stop` hook; uncorrelated failure modes covered by both paths
- **Decision Reports** — every component documents its reasoning in a schema-validated stream, routed through the evaluator (the sole memory writer) for persistence

**Twenty-one named failure modes** cover the predictable ways the system fails — most are interaction failures between components rather than component-internal bugs.

## Build status

All fifteen acceptance scenarios pass against a live `claude -p` subprocess. See [architecture2.md section 12](architecture2.md#12-build-status--what-was-actually-implemented) for the full record, including where the implementation deliberately diverged from the design (the steering control surfaces were built as **hooks plus an MCP server** rather than as Claude Code subagents — the cleaner integration surface in practice).

| # | Scenario | What it exercises |
|---|----------|-------------------|
| 1 | Walking skeleton | end-to-end data flow, Decision Reports to memory |
| 2 | Refinement run | multi-cycle, seeder multi-lens reflection, `REFINEMENT_COMPLETE` |
| 3 | Reactive steering | `Stop`-hook halt router catches halt-language, brain resolves, framework continues |
| 4 | Proactive steering | framework calls `consult_director`, brain answers, no halt |
| 5 | Context steward | token tracking → `suggest_compact` with preservation guidance |
| 6 | Triage rejection | Stage-2 classifier rejects a goal with no software deliverable |
| 7 | Triple-check | hard-call escalation: answer → critique → reconcile |
| 8 | Multi-hat evaluator | Layer-2 panel (Correctness / Adversary / User-intent), Adversary veto |
| 9 | Decision Reports queryable | `memory.query_reports` filtering by component / type / flag |
| 10 | Dispatch lock | prevents the proactive and reactive paths from double-firing |
| 11–14 | Hardening scenarios | incl. post-hoc dispatch-escape detection (scenario 13, FM-18) |
| 15 | Seeder validation gate | fixture-based human-agreement measurement (~83%) |

The current build uses in-process memory and a keyword-triggered brain escalation as legitimate v1 implementations of the architecture's interfaces; both are designed as swaps (SQLite + vector memory; LLM-reflective escalation) rather than rewrites.

## Getting it running

See **[OPERATIONS.md](OPERATIONS.md)** — install prerequisites, authenticate the `claude` CLI for headless use, run the acceptance suite, and drive your own Run.

## Lineage

This project emerged from a multi-model conversation in May 2026, with contributions from Claude, ChatGPT, and Gemini. Each pushed against the others' framings, and the architecture is the surviving structure.

Conceptual ancestors:

- **Actor-critic architectures** (Sutton & Barto) — the evaluator is the critic
- **Self-play loops** (AlphaZero and successors) — the closed-loop pattern
- **Reflection agents** (Shinn et al. 2023) — the seeder's multi-lens reflection
- **Tool-using agents with environmental feedback** (ReAct, Toolformer) — the grounding layer
- **Sovereignty, Spine Reborn, Skynet, Growing Spine** (this author) — the lineage of persistent-memory agents this builds on
- **Deming's PDCA + statistical process control** — the design principle that quality is built into the process, not inspected in afterward

## Repository layout

```
Synthetic/
├── README.md                 — this file
├── OPERATIONS.md             — install + usage manual
├── CLAUDE.md                 — Claude Code project guide (build-time orientation)
├── architecture2.md          — the locked v1.5 architecture (source of truth) + build-status addendum
├── architecture.md           — historical v0.1 design (preserved for lineage)
├── architecture.svg          — v0.1 Spine Loop diagram (historical)
├── research-findings.md      — web-research-backed TBD resolutions feeding v1.0–v1.2
├── pyproject.toml            — package + pytest config (markers, paths)
├── LICENSE                   — MIT
│
├── synthetic_user/           — the control wrapper (the brain of the system)
│   ├── orchestrator.py       — drives one Run end-to-end; owns state + report buffer
│   ├── triage.py             — request router (loop / reject), Stage-2 classifier
│   ├── seeder.py             — cycle-boundary reflection + cold-start
│   ├── brain.py              — steering brain: routine dispatch + triple-check escalation
│   ├── evaluator.py          — 3-layer reliability eval, multi-hat panel, sole memory writer
│   ├── steward.py            — context-pressure tracking
│   ├── memory.py             — Decision Report store + query interface (in-process v1)
│   ├── reports.py            — Decision Report schema + per-Run buffer
│   ├── executor.py           — ClaudeCodeExecutor: drives `claude -p`, resumes sessions
│   ├── types.py              — shared vocabulary (Run, Cycle, Route, StopCode, …)
│   ├── config.py             — tunable constants + per-role model tiers
│   └── utils.py
│
├── hooks/                    — Claude Code hook handlers (the interception surface)
│   ├── session_start_handler.py  — injects operating instructions
│   ├── stop_handler.py           — reactive steering on halt-language
│   ├── router.py                 — halt-language classifier
│   ├── pre_tool_use_handler.py   — action-pattern triggers
│   ├── post_tool_use_handler.py  — steward monitor
│   └── state.py                  — per-Run IPC: hooks log, dispatch lock, token counter
│
├── director_mcp/             — the proactive steering path
│   └── consult_director_server.py — FastMCP server exposing consult_director
│
├── .claude/settings.json     — hook wiring + MCP tool permission (committed)
├── .mcp.json                 — project-scope MCP server registration (committed)
│
└── tests/                    — one acceptance test per scenario
    ├── test_scenario_01.py … test_scenario_15.py
    └── fixtures/scenario_15_human_verdicts.json
```

## License

MIT. See [LICENSE](LICENSE).
