# Synthetic User

> A closed-loop control system that wraps an existing agentic framework (Claude Code as v1 reference) with infrastructure replacing the human roles that ordinarily sit around such a loop.

**Status: ARCHITECTURE LOCKED at v1.2. Implementation begins.**

## What it is

Agentic frameworks like Claude Code do real work, but a human still has to drive them from outside: triaging incoming requests, deciding what to work on, watching and answering questions, managing context, and reviewing afterward. Synthetic User replaces that human layer with a structured set of components, each with bounded authority, all bound by reality through the framework's real tool calls.

The system replaces six distinct human roles around an agentic framework:

- **Triage gate** \u2014 routes incoming requests (loop / direct-handle / reject)
- **Seeder** \u2014 cycle-boundary multi-lens reflection + cycle preparation
- **Steering brain** \u2014 in-flight resolution of framework doubts and action patterns
- **Context steward** \u2014 continuous context monitoring during execution
- **Evaluator** \u2014 post-hoc learning, schema validation, audit trail
- **Decision Reports** \u2014 structured reasoning audit substrate across all components

The agentic loop itself \u2014 planning, tool use, code generation, verification \u2014 is **inherited from the framework** (Claude Code in v1). Synthetic User does not reinvent agentic loops; it wraps existing ones.

## What it isn't

**Not an attempt to remove humans from agentic systems.** The system replaces specific cognitive roles around the loop, not the human as beneficiary of the work.

**Not an alignment experiment.** Components optimize reliability and audit trail, not morality. "Did this work?" not "was this good?"

**Not AGI.** It is a self-updating control system around an existing framework. That is interesting on its own terms.

**Not a continuation of [Growing Spine](https://github.com/Tubifix77/growing-spine).** Same era, same author, related lineage, different hypothesis. Growing Spine is a creature with one constraint and no enforcement layer. Synthetic User is a closed loop with explicit roles, schemas, and audit substrate.

## Architecture (v1.2 LOCKED)

The buildable architecture lives in [architecture2.md](architecture2.md). Twelve revisions across the design phase: v0.1 (initial five-component decomposition) \u2192 v0.9 (context steward + cycle preparation) \u2192 v1.0 (CC hook binding + hybrid synth-user dispatch) \u2192 v1.1 (Decision Reports as audit substrate) \u2192 v1.2 (acceptance-test-driven implementation strategy + all TBDs resolved).

**Key concepts:**

- **Run** \u2014 one bounded Synthetic User goal-pursuit, made of one or more cycles, terminates on a seeder stop code
- **Cycle** \u2014 one seeder \u2192 framework execution \u2192 evaluator scoring iteration; maps 1:1 to a Claude Code "turn"
- **Hybrid synth-user dispatch** \u2014 proactive entry via `SessionStart` hook + reactive entry via `Stop` hook; uncorrelated failure modes covered by both paths
- **Decision Reports** \u2014 every component documents its reasoning in a schema-validated stream, routed through the evaluator for memory persistence

**Sixteen named failure modes** plus FM-17 (Decision Report inflation) cover the predictable ways the system fails \u2014 most are interaction failures between components rather than component-internal bugs.

## The hypothesis being tested

Two LLMs talking to each other almost always collapse into a closed epistemic loop: internally coherent, externally wrong. The standard objection to multi-agent self-play is that it generates plausible nonsense at scale.

The claim this project tests: **a closed loop becomes stable when external reality is allowed to disagree with it often enough, AND when each component's reasoning is documented in a form a human can audit without replaying the system.**

Concretely \u2014 given triage + seeder + brain + steward + evaluator + real tool execution + persistent memory + Decision Reports, can the system improve at a non-trivial task over time without drifting into reward-hacking, hallucination ecosystems, or goal collapse?

If yes: this is a viable training-data-free agent improvement pattern.  
If no: the failure modes themselves are the contribution \u2014 they map the boundary between useful self-play and pure self-talk.

## Implementation strategy

[architecture2.md](architecture2.md) section 10 is the entry point for the build phase.

Build is **acceptance-test-driven**:

1. Twelve baseline acceptance scenarios are locked at v1.2 (section 10.3)
2. Walking skeleton passes scenario 1 only; each subsequent scenario drives component growth
3. Three test layers: acceptance scenarios (primary), contract tests on interfaces (defense in depth), targeted unit tests for deterministic gnarly logic
4. **Mocking LLM-calling components is explicitly rejected** \u2014 the interaction with real model behavior IS what's being tested

Recommended build order: scenarios 1 \u2192 2 \u2192 3 \u2192 4 \u2192 6 \u2192 9 \u2192 10 \u2192 5 \u2192 7 \u2192 8 \u2192 11 \u2192 12.

## Lineage

This project emerged from a multi-model conversation in May 2026, with contributions from Claude, ChatGPT, and Gemini. Each pushed against the others' framings, and the architecture is the surviving structure.

Conceptual ancestors:

- **Actor-critic architectures** (Sutton & Barto) \u2014 the evaluator is the critic
- **Self-play loops** (AlphaZero and successors) \u2014 the closed-loop pattern
- **Reflection agents** (Shinn et al. 2023) \u2014 the seeder's multi-lens reflection
- **Tool-using agents with environmental feedback** (ReAct, Toolformer) \u2014 the grounding layer
- **Sovereignty, Spine Reborn, Skynet, Growing Spine** (this author) \u2014 the lineage of persistent-memory agents this builds on
- **Deming's PDCA + statistical process control** \u2014 the design principle that quality is built into the process, not inspected in afterward

## Repository layout

- [architecture2.md](architecture2.md) \u2014 the locked v1.2 architecture (source of truth)
- [architecture.md](architecture.md) \u2014 historical v0.1 design (preserved for lineage)
- [architecture.svg](architecture.svg) \u2014 v0.1 Spine Loop diagram (historical)
- [research-findings.md](research-findings.md) \u2014 web-research-backed TBD resolutions that fed into v1.0\u2013v1.2
- LICENSE \u2014 MIT

## License

MIT. See [LICENSE](LICENSE).
