# Synthetic User — Architecture v1.3 (IMPLEMENTATION-READY)

**Status: IMPLEMENTATION-READY — design complete, the Claude Code integration mechanism is now specified (section 2.9), and all eight pre-implementation audit findings are resolved (section 8). Build begins from this document.**

Twelve revisions across the design phase: v0.1 (initial five-component decomposition) → v0.9 (context steward + cycle preparation) → v1.0 (CC hook binding + hybrid synth-user dispatch) → v1.1 (Decision Reports as audit substrate) → v1.2 (acceptance-test-driven implementation strategy + all TBDs resolved).

All design TBDs are resolved, and a v1.3 pre-implementation audit closed eight further holes (most importantly: the v1.0–v1.2 dispatch design assumed a Claude Code hook that does not exist; v1.3 re-grounds proactive dispatch on an MCP tool). Section 2.9 specifies exactly how the wrapper attaches to Claude Code. Section 10 (Implementation Strategy) is the entry point for the build phase. Section 8 retains the full decision history.

**What this is.** A closed-loop agent architecture that wraps an existing agentic framework (Claude Code as v1 reference) with infrastructure that replaces the human roles ordinarily sitting around such a loop. The framework does the cognitive work inside cycles; this project builds the substitutes for the human who would otherwise drive the framework from outside.

**Project naming note.** "Synthetic User" is the project name. Inside the project, the components have specific names: **triage gate** (request screening), **seeder** (cycle-boundary reflection, goal generation, and cycle preparation), **steering brain** (in-flight resolution), **context steward** (continuous context monitoring), **evaluator** (post-hoc learning). The project replaces the human user; the components handle specific slices of that replacement.

**For version history, see section 10 (changelog).**

## 0. Vocabulary

This architecture wraps Claude Code (v1 reference framework). Where our component names collide with CC's native terms, the mapping is:

| Our term | CC native term | What it means |
|----------|---------------|---------------|
| Tool call | Tool call | One tool invocation (read, edit, bash, etc.). CC fires `PreToolUse`/`PostToolUse` hooks around it. |
| Cycle | **Turn** | One complete cycle from CC's perspective: user message in → reasoning → N tool calls → final response. May contain 15–20 tool calls. `Stop` hook fires at the end. |
| Run | (no CC equivalent) | One bounded Synthetic User goal-pursuit. One or more cycles/turns, terminates on seeder stop code. Lives entirely in the wrapper layer. |
| (Synthetic User has no concept above Run) | Session | One CC `session_id`, with its own transcript at `~/.claude/projects/`. Begins with `SessionStart` hook. **v1 maps exactly one Run to one session** (see rule below). |

**Why two terms for one thing (cycle/turn).** "Cycle" describes the Synthetic User wrapper's view: seeder generates prompt → framework executes → evaluator scores. "Turn" describes CC's view: user-prompt-to-final-response. They refer to the same boundary from different sides. Throughout this doc, "cycle" is used when describing wrapper-level flow; "turn" when describing CC's internal lifecycle (hooks, compaction, etc.).

**Run ↔ session mapping (resolved v1.3): one Run = one CC session.** A Run's cycles are consecutive turns inside a single CC session. The orchestrator opens a session when a Run begins, drives turn N+1 by submitting the seeder's next-cycle goal as a new prompt to that same session, and ends the session when the seeder stops the Run. The earlier table language ("a session may host multiple Runs") described a future optimization; v1 is strictly one Run per session, which keeps session lifecycle, transcript scope, and hook installation unambiguous.

**CC integration surface used by this architecture.** The wrapper attaches to Claude Code through exactly two CC-native extension mechanisms — **hooks** and **one MCP tool**. Section 2.9 specifies the full surface; the summary:

- **`consult_director` MCP tool** — the *proactive* synth-user dispatch. CC is instructed (at session start) to call this tool instead of asking the user; the call is synchronous, so the brain answers in-turn with no halt. This replaces the v1.0–v1.2 `[steering-director:]` string-emission idea, which assumed a hook that fires on arbitrary mid-turn text (no such hook exists).
- `Stop` (fires at the end of every turn, cannot be skipped) — evaluator entry point AND the *reactive* synth-user fallback. When CC asked the user instead of calling the tool, the Stop handler classifies the message and, if it is a halt, returns block-with-reason so CC continues in the same session.
- `PreToolUse` (fires before each tool call) — action-pattern trigger surface for the steering brain (allow / deny / inject-context).
- `PostToolUse` (fires after each tool call) — the context steward's monitoring and intervention surface (per-tool-call granularity, not mid-thought).
- `PreCompact` (fires before CC's own compaction) — lets the steward supply preservation guidance to CC's built-in autocompact.
- `SessionStart` (fires when the orchestrator opens a session for a Run) — injects the `consult_director` instruction and any standing deployment rules.
- `UserPromptSubmit` (fires when the orchestrator submits a prompt) — how the orchestrator starts each cycle's turn within the session.

## 1. Core concept

A closed-loop agent with five functional components, grounded by an external layer, fronted by an auxiliary triage gate.

**This system does not build an agentic loop.** An external **agentic framework** is the agentic loop. The synthetic-user project builds the *infrastructure that wraps* an existing agentic framework in a closed system, replacing the human roles that ordinarily sit around such a loop.

**The v1 reference framework is Claude Code.** The architecture is framework-agnostic in principle — any equivalent agentic framework that exposes planning, tool use, verification, and interceptable pause moments would work. The wrapper components below refer to "the framework" generically; Claude Code is the implementation target for v1 because it's mature, in active use, and exposes the required surfaces cleanly.

The clean cut: **The framework does the cognitive work inside a cycle. Synthetic-user replaces the human who would normally drive the framework from outside.**

The human plays six distinguishable roles in normal framework use:

- The human who *triages incoming work* (decides whether something is loop-worthy) → **triage gate** (auxiliary, outside the loop)
- The human who decides *what to work on once a job is accepted, and prepares the cycle to run efficiently* → **seeder**
- The human who does the work → **handled by the framework itself**, not replaced
- The human who *watches and answers* during the work → **steering brain**
- The human who *manages context as a continuous resource* during the work → **context steward**
- The human who *reviews after the fact and learns* → **evaluator**

All six are bound by a **non-negotiable external world** — real tools, real APIs, real errors — that prevents the loop from collapsing into self-talk. The framework's own tool calls supply this layer automatically; the synthetic-user wrapper does not need to build it.

Three things make this different from a chatbot talking to a chatbot:

1. **The world is real.** Tool outputs come from actual code execution, actual APIs, actual file system state. The framework already handles this.
2. **The steering brain has narrow, well-defined authority.** It resolves in-flight situations the framework can't resolve on its own. Most of the framework's pauses are handled by the framework itself; the brain is escalation.
3. **Memory persists with structure and write-gating.** Only the evaluator writes. Everyone else reads. The framework does not provide cross-session persistent memory by default; this is one of the things we add.

The triage gate is the only point in the architecture where the system can communicate back to the goal source. The inner loop has no human in it by design; the gate sits outside the loop and is allowed to refuse work or request clarification, because doing so does not contaminate the closed-loop hypothesis (the loop has not started yet at the time the gate decides).

## 1.5 What is inherited, built, and configured

The honest inventory of where work lives.

**Inherited from the framework (no design work needed):**

- The agentic loop itself (gather context → take action → verify results, repeat)
- Tool use, code generation, file system access, web search
- In-session memory and context handling primitives (auto-compact at limits, `/compact`, `/clear`, subagent delegation)
- Most action-pattern detection — the framework already pauses before destructive operations, flags before risky commits, verifies before deletions. The synthetic-user system intercepts these existing pause moments rather than detecting new ones.
- The "executor" role from prior architecture versions is entirely the framework. We do not build an executor.

For v1, the framework is Claude Code. The wrapper would work over Cursor, Aider, or any equivalent framework that exposes the same surface.

**Built by us (genuinely new code):**

- **Triage gate.** Sits in front of the framework, routes incoming requests to loop / direct-handle / reject.
- **Cycle wrapper / orchestrator.** Runs the framework in cycles instead of one-shot sessions. Handles handoff between cycles, session lifecycle, applies cycle preparation from the seeder, terminal output to goal source.
- **Seeder reflection + preparation logic.** A multi-lens reflection that runs at the cycle boundary, performs creative review, and either generates the next cycle's goal (with cycle preparation: specificity, tool config, subagent opportunities) or stops the session.
- **Steering brain dispatch.** The logic behind the `consult_director` MCP tool and the `Stop`/`PreToolUse` hook handlers (section 2.9): it holds the triple-check lock, invokes The Prompt when escalation is needed, and returns verdicts. The framework handles most situations on its own; the brain dispatch only fires when the framework would have asked the user or is about to take a registered action.
- **Context steward.** Continuous monitor of framework context state during cycle execution. Intervenes when context quality is at risk — suggests compact, clear, delegate to subagent, or interrupt. Runs in parallel with the framework; goes quiet when context is healthy.
- **Evaluator.** Post-hoc analyzer that scores cycles, attributes failure, updates trigger weights and brain priors, consolidates memory. The largest single new build.

**Configured / specified, implemented off-the-shelf:**

- **Persistent memory stores.** Probably memory MCP or SQLite-backed; deployer chooses. We specify the four-store structure (episodic, semantic, strategy, failure); we do not implement storage.
- **Observation surface.** Logs, dashboard, journal, scheduled summaries. We specify what gets surfaced; deployer chooses the UI.
- **Model selection per role.** Deployer's choice. v1 reference: Claude tiers across roles (Haiku for triage and context steward, Sonnet for seeder/brain dispatch routine cases, Opus for evaluator and Layer 6 escalations).

**Deployment decisions (not architecture):**

- **Task domain.** Domain-agnostic. Whatever the framework can do, the wrapper can run cycles over.
- **Run model.** Run-model-agnostic. Continuous daemon, scheduled bursts, or interactive sessions all work.
- **Cold-start goal source.** Human prompt, agent queue, file backlog, autonomous generation, corpus.

This inventory is the honest scope of new work for v1. Six things to build. Three things to specify. Three deployment decisions for whoever runs this. Everything else rides on the framework's existing capabilities.

## 2. Components

### 2.0 Triage gate (auxiliary, outside the loop)

**Function.** Runs once per incoming request, before cycle 0. Classifies the request into one of three routes and acts accordingly.

**The three routes.**

- **Loop-worthy → enter cycle 0.** Multi-step work requiring planning, tool use, or verification. The goal is passed to the seeder verbatim. The synthetic-user engine handles it from there.
- **Simple lookup → direct handle.** Single-fact queries, current-data queries, basic web searches, definitions. Handled outside the loop with a direct tool call, returning the result without engaging the cycle machinery.
- **Malformed or too vague → reject with clarification request.** The goal source receives a structured response indicating why the request could not be acted on and what context is missing.

**Inputs.**
- Raw request text from the goal source

**Outputs.**
- Routing decision (loop / simple / reject)
- For loop route: the goal, unchanged, passed to the seeder
- For simple route: the direct response, returned to the goal source
- For reject route: a structured clarification request (`rejection_reason`, `missing_context`, `suggested_clarification`)

**What the gate does NOT do.**
- Does not modify the input. Triage is categorization, not transformation.
- Does not "improve" the question. An earlier design considered running The Prompt as a goal-improvement preprocessor and was rejected because LLM-based input refinement without an asker present produces hallucinated context, not real clarification.
- Does not store state across requests. Each triage decision is independent.
- Does not enter the loop. It is auxiliary infrastructure that lives in front of the engine.

**Implementation options (TBD-9).** Pure rule-based classifier, small LLM call, or hybrid (rules for clear cases, LLM fallback for ambiguous ones). All decisions are logged in episodic memory for the evaluator to audit.

**Replaces what human did.** The human glancing at an incoming request and deciding whether it's worth the full project treatment or just needs a quick answer.

### 2.1 Seeder (cycle-boundary reflection + cycle preparation)

**Function.** Runs at the cycle boundary — after the evaluator scores cycle N, before any potential cycle N+1. Performs creative reflection on cycle N's deliverable, and if continuing, prepares cycle N+1 for context-efficient execution.

**The seeder is one activity, not two.** Earlier architecture versions framed the seeder as "review then generate" — two distinct steps. v0.8 recognized that real creative reflection produces direction as a natural consequence. The decision (continue / stop / what direction) emerges from the reflection rather than being a separate downstream step. v0.9 extends this further: when the seeder decides to continue, it also produces cycle preparation as part of the same reflection — the lenses that identified the next direction also identified how the cycle should be configured to pursue it efficiently.

**At cycle 0 (cold start):** Pure pass-through with minimal preparation. The triage gate has already validated the request. The seeder hands the goal to the framework verbatim, optionally with default cycle preparation if the deployment has standing rules (e.g., default MCP set). No reflection at cycle 0 — there is no prior cycle to reflect on.

**Evaluation-criteria source (resolved v1.3).** The evaluator scores against *declared* criteria, so something must declare them. At **cycle 0**, the cycle wrapper prepends a one-line criteria-declaration step to the goal: CC is asked to state explicit done-when conditions before beginning work ("before starting, list the concrete conditions that would make this task complete"). The orchestrator captures that declaration and hands it to the evaluator as cycle 0's criteria. At **cycle N>0**, the seeder's cycle preparation carries the criteria for that cycle — the lenses that identified the next direction also define what "done" means for it. This closes the gap where cycle 0 would otherwise have no criteria beyond "a deliverable exists."

**At cycle boundaries (after cycle N completes, before cycle N+1):** Multi-lens reflection + cycle preparation.

**The multi-lens reflection model.**

The seeder applies multiple evaluative stances to cycle N's deliverable, each surfacing different aspects of what might come next. The lenses are not a checklist — they are *perspectives* that produce different views of the same work.

**The lenses:**

1. **Comparative.** What have others done in similar projects? What approaches did the field take that this cycle didn't? What did the field consider but reject, and why? This is the lens that brings external knowledge the framework didn't have time to consult during the cycle. Typically uses web search.

2. **Aspirational / philosophical.** What would prominent views on this kind of work suggest comes next? If multiple thoughtful perspectives looked at this, what would they collectively recommend? This surfaces directions that come from values or principles, not just from gap-detection.

3. **Creative.** If a creative artist or designer looked at this deliverable, what does it lack? What unexpected move would make it more than what was asked for? This catches cases where the work is technically complete but missing something a strict-criteria review wouldn't flag.

4. **Production.** From a professional production standpoint, what does this need before it ships? What corners were cut that need filling in? This is the pragmatic refinement lens — the one that catches the "first build is rough" cases.

5. **Skeptical.** What's the strongest case that this work is actually done, and that further cycles would be gold-plating? This lens advocates for stopping. When the skeptical lens makes a stronger case than the others, the session ends.

6. **User-perspective** (optional, deployment-dependent). What would the eventual user notice as missing, confusing, or rough? The closest the seeder gets to projecting forward to who consumes the output.

**Lens selection.** The seeder does not always run all six. It selects lenses relevant to the cycle's deliverable type. A documentation cycle probably skips the comparative lens; a feature cycle probably needs it. v1 ships with default lens selection rules; tuning is the evaluator's job.

**Synthesis.** After each chosen lens produces its perspective, the seeder synthesizes:

- Do the lenses converge on a direction? → That direction becomes the goal for cycle N+1.
- Do the lenses disagree, with one clearly stronger? → The strongest view wins; the disagreement is recorded.
- Does the skeptical lens make the strongest case? → `no_next_goal` with a reason code.
- Do the lenses produce only weak, vague, or self-referential suggestions? → `no_next_goal: circular`.

**Cycle preparation (when continuing).** When the synthesis produces a new goal, the seeder also prepares the cycle for context-efficient execution. Three sub-tasks:

1. **Specificity check.** The seeder reviews the generated goal and sharpens it. Vague prompts cost more context than detailed ones because the framework has to explore to figure out what's meant. The seeder uses the cycle N-1 context (it has full knowledge of files, structure, prior decisions) to make the goal concrete: specific functions to modify, specific gaps to address, specific edge cases to handle.

2. **Tool configuration recommendation.** The seeder considers what tools the cycle will need. Unused MCPs load tool descriptions into context unnecessarily. The seeder recommends which MCPs should be enabled and which disabled for this cycle. A pure refactoring cycle doesn't need the database MCP loaded; a deployment cycle doesn't need the design-tool MCP. The cycle wrapper applies this configuration before the framework session starts.

3. **Subagent opportunity identification.** The seeder reviews the goal and marks sub-tasks that would benefit from subagent delegation. "Investigate the structure of the authentication system to understand the imports" is a subagent task — the result is needed, but the exploration would pollute main context. "Refactor the user model" is main-context work. The seeder marks these in the task prompt itself, so the framework starts the cycle already knowing what to delegate.

These three preparation tasks are part of the same reflection pass — the seeder uses the same context (multi-lens output, cycle N-1 state, goal direction) to produce both the new goal and its preparation.

**Outputs:**

- **New goal for cycle N+1 with cycle preparation:**
  ```
  {
    "decision": "new_goal",
    "new_goal": "<goal text>",
    "task_prompt": "<specific, well-prepared prompt>",
    "cycle_config": {
      "recommended_mcps": ["<list to enable>"],
      "disabled_mcps": ["<list to disable>"],
      "subagent_opportunities": [
        {"scope": "<task>", "rationale": "<why subagent>"}
      ]
    },
    "rationale": "<one paragraph explaining the decision and preparation>"
  }
  ```

- **`no_next_goal` with reason code:**
  - `refinement_complete` — skeptical and production lenses agree the work ships as-is. Normal stop after refinement cycle.
  - `complete` — all lenses converge on "done". Rare; cycle 0 was already finished.
  - `circular` — lenses produce suggestions that overlap with prior cycles' work.
  - `no_new_input` — lenses produce nothing because there's nothing new to react to.

**The natural session shape (unchanged from v0.5).** For most accepted requests:

1. Cycle 0 — build the thing
2. Cycle 1 — refine the thing
3. Stop with `refinement_complete`

**The refinement-of-refinement threshold lives inside the skeptical lens.** The skeptical lens checks session history: has this deliverable already been refined once? If yes, the bar for proposing further refinement is high.

**What the reflection does that the evaluator does not.** The evaluator scores against declared criteria. The seeder's reflection asks: "what is the next direction worth taking, considered from multiple stances?" These are different evaluations.

**Why it's separate from the evaluator.** The evaluator has consistency bias. The seeder reflects from outside that incentive.

**Implementation note.** The multi-lens reflection maps onto The Prompt's structure. The seeder is likely implemented as a Prompt invocation with specific lens-selection guidance and preparation instructions appended.

**Cost note.** Multi-lens reflection plus cycle preparation is more expensive than a structured rubric. Justified because cycle-boundary decisions are the highest-leverage reasoning the system does. The preparation work is essentially free — it uses the same context the reflection already loaded, just produces additional structured output.

**Replaces what human did.** The human looking at finished work, asking "what's next, in what direction, at what depth, or is this done?" — AND the human writing a specific prompt, deciding which MCPs to disable, and identifying subagent opportunities before starting the next session.

### 2.2 Executor (inherited from the framework)

**Function.** Decomposes goals into action sequences, calls tools, produces deliverables. This is the agentic loop itself.

**Implementation.** Entirely the framework's job. For v1, Claude Code. Nothing in this section is new code.

**Pre-prompt instruction (proactive entry, re-grounded v1.3).** Every CC session begins with the universal trigger instruction, injected via the `SessionStart` hook: *when you would have asked the user a question to proceed, instead call the `consult_director` MCP tool with your question and current context, and continue based on the result it returns.* Because MCP tool calls are synchronous request–response, the brain answers in-turn and CC never halts. This replaces the v1.0–v1.2 `[steering-director:]` design, which assumed a hook firing on arbitrary mid-turn text; no such hook exists (see section 2.9).

**Why this needs a backup (Stop-hook router, section 2.4).** The SessionStart instruction degrades as CC's context compresses across many turns; by turn 30+ in a long run its salience may fade and CC may simply ask the user instead of calling the tool. The reactive `Stop`-hook path catches those: the Stop handler classifies the final message and, if it is a halt, returns block-with-reason so CC continues in the same session with the brain's answer injected. Both paths share dispatch logic; only the entry point differs.

**Subcomponents (provided by the framework, not built):**
- Planner
- Tool router
- Code generator (when relevant)
- Reflection / self-critique (the framework's built-in features)
- Native context management primitives (auto-compact, slash commands, subagent delegation)

**Replaces what human did.** The human doing the actual work. Not replaced by us; replaced by the framework.

### 2.3 External world (grounding layer)

**This is the most important component.** Without it the entire system reduces to two LLMs writing fiction at each other.

**What it includes.**
- Code execution runtime (subprocess, sandbox, container)
- APIs (third-party services, deterministic responses)
- File system (real reads, real writes)
- Network tools (search, fetch, ping)
- Simulation environments where physical reality isn't available

**What it produces.**
- Results `R` (whatever the tool returned)
- Errors `E` (when things failed)
- State changes `S` (what's now different in the world)

**Crucial property.** This layer is non-negotiable from the system's perspective. The LLMs can rationalize anything, but they cannot rationalize a non-zero exit code into a zero exit code. This is what prevents loop collapse.

**Inherited.** The framework already calls real tools and gets real results. We do not build this layer.

### 2.4 Steering brain (in-flight resolver)

**Function.** Resolves in-flight situations during a cycle. One component, multiple trigger surfaces, one shared resolution logic.

**Trigger surfaces.** The brain is invoked from three kinds of triggers, mapped to CC's hook surface. Each entry point feeds the same brain logic with the same normalized payload.

**Trigger Type 1 (proactive): Framework doubt, caught in-turn via the `consult_director` MCP tool.** The `SessionStart` instruction tells CC to call `consult_director(question, context)` instead of asking the user. CC calls it mid-turn; the call blocks; the orchestrator runs the brain; the verdict returns as the tool result; CC continues without halting. Synchronous MCP semantics make this the cheap, common case. (This is the v1.3 correction of the original "emit a magic string a hook catches" design — see section 2.9.)

**Trigger Type 2 (reactive): Framework doubt, caught at turn end.** When the proactive path fails (CC ignored the SessionStart instruction and just asked the user), CC ends the turn with a halt disguised as a final response ("I need to ask..."). The `Stop` hook fires. The **Stop-hook router** (sub-mechanism, below) classifies the final message: if it is a halt, route to brain; else route to evaluator. The brain produces a verdict and the Stop handler returns `{"decision": "block", "reason": "<verdict>"}` — CC's native Stop-hook semantics inject the reason and **continue the same session** (no new prompt is synthesized). This corrects the earlier description, which alternately called the resume a "synthesized follow-up `UserPromptSubmit`"; the real mechanism is block-and-continue.

**Trigger Type 3: Action pattern match.** A registered action-pattern skill detects CC is about to perform an action of interest (matched via CC's `PreToolUse` hook). The skill routes to the brain. The brain receives the about-to-happen action and returns proceed/redirect/halt.

These three feed the same brain. The triggers are heterogeneous; the judgment is unified.

**Why both proactive and reactive instead of picking one.** Each path fails in uncorrelated ways. The proactive instruction degrades over long sessions as CC's context compresses and pre-prompt salience fades. The reactive `Stop` hook depends on detectable halt-language in CC's response — brittle if CC phrases halts in novel ways. The hybrid covers both failure modes at the cost of a small router and a shared dispatch lock. This is the resolution of v0.9's open question about which dispatch mechanism to standardize.

**Normalized payload.** Each trigger normalizes its input before handing to the brain:

```
{
  "trigger_type": "framework_doubt" | "action_pattern",
  "trigger_detail": <the question, or the about-to-action>,
  "framework_state": <current trajectory, recent actions>,
  "goal": <original goal, verbatim>,
  "constraints": <declared constraints>,
  "memory_relevant": <relevant retrievals>
}
```

**Normalized output.** The brain returns a structured verdict in one of three shapes:

- `proceed` — the framework continues as planned
- `redirect(pointer_to_existing_context)` — the framework continues, but first re-reads the pointed-to context
- `halt(reason)` — the framework stops and the cycle is aborted with a recorded reason

**v1 implementation: framework's reasoning as default, The Prompt as escalation.**

The brain's primary reasoning engine is **the framework itself**. Most situations the brain receives are ones the framework can resolve internally. The escalation path uses **The Prompt** with web search enabled — invoked when the framework's normal reasoning would not be enough.

The hypothesis: for ~99% of in-flight situations, the framework's own reasoning is sufficient. The Prompt's heavier machinery is reserved for the ~1% where the question genuinely requires systematic external grounding.

**The brain dispatch wrapper.** Small layer that handles trigger payload normalization, verdict normalization, escalation detection, and triple-check state tracking for Layer 6. Also holds the dispatch lock shared with the Stop-hook router (below).

**The Stop-hook router (new in v1.0).** Sub-mechanism handling Trigger Type 2's classification problem. The `Stop` hook fires at the end of every turn, and has two possible destinations: evaluator (normal turn completion) or brain (halt disguised as completion). The router decides which.

Implementation follows TBD-9's triage-gate cascade pattern:

1. **Stage 1: Rules.** Regex over CC's final response. Patterns: "I need to ask", "could you clarify", "should I", "do you want me to", "which would you prefer", etc. Handles ~95% of halts (the obvious ones). Free, <1ms.
2. **Stage 2: Haiku classifier.** When Stage 1 is ambiguous (response *might* be a halt). Single Haiku call, ~200-500ms, ~$0.0001. Returns `halt` | `completion` | `unclear`.
3. **Stage 3: Default to completion.** If Stages 1 and 2 don't decide, treat as completion and route to evaluator. The evaluator's audit will catch missed halts post-hoc; cost of misclassification at this stage is one extra refinement cycle, not silent failure.

**Lock interaction with the seeder.** When the Stop-hook router routes to brain, the dispatch lock is acquired. The seeder's next cycle-boundary reflection checks the lock state: if a brain dispatch handled the cycle's terminal state, the seeder treats the cycle as continuing rather than completed, and skips its normal multi-lens reflection for this boundary. Prevents double-firing (FM-10 update).

**Layer 6 sovereignty: triple-check, not human escape.**

When Layer 6 fires from a top-level escalation:

1. **Pass 1:** The Prompt runs on the question. Produces an answer.
2. **Pass 2 (critique):** The Prompt runs again, with Pass 1's answer as input. Web search invoked.
3. **Pass 3 (reconciliation):** The Prompt runs a third time, with Pass 1 and Pass 2 as input.

The Pass 3 verdict is returned to the framework. The cycle continues normally. Reality validates post-hoc via the evaluator.

**Recursion protection: the dispatch lock.** A binary `in_triple_check` flag held by the dispatch wrapper prevents nested triple-checks. While the lock is held, any Layer 6 escalation arising inside Pass 1, 2, or 3 contributes its content to the current pass but does not bootstrap a new nested triple-check.

**Recording for the evaluator.** Each triple-check fire is flagged in episodic memory.

**Authority.**
- Can halt the framework (on irreversible operations or hard constraint violations)
- Can redirect attention to existing context
- Cannot escalate to the human — structurally forbidden
- Cannot inject new context

**Critical framing.** The brain is operational, not ethical. It decides what should happen, not what is good.

**Replaces what human did.** The human watching the screen and the human answering the framework's questions.

### 2.5 Evaluator (post-hoc learner)

**Function.** Runs once per cycle, after the cycle completes. Seven sub-functions:

1. **Reliability evaluation.** Scores the cycle against declared criteria. (Criteria source resolved in v1.3: cycle 0's criteria come from CC's own done-when declaration captured by the wrapper; cycle N>0's criteria come from the seeder's cycle preparation — see section 2.1.)
2. **Failure attribution.** When something went wrong, identifies which subsystem caused it.
3. **Trigger set adjustment.** Updates the action-pattern skill set.
4. **Brain prior adjustment.** Updates the steering brain's resolution priors.
5. **Steward intervention audit.** Reviews context steward decisions during the cycle. Did the compact help or hurt? Did the suggested subagent delegation save context without losing fidelity? Tunes the steward's intervention thresholds over time.
6. **Memory consolidation.** Compresses episodic events into reusable strategies.
7. **Decision Report ingestion (new in v1.1).** Drains the per-Run report buffer at cycle close. Validates each report against its component's schema. Persists validated reports to memory. Flags malformed reports for self-review (a new finding type). Generates a self-report documenting its own scoring/attribution decisions (the only `self_reported=true` write in the system).

**Audits the seeder.** The evaluator also reviews the seeder's reflection from cycle N-1's boundary — did the chosen direction prove valuable? Were the lenses well-selected? Did the stop decision land at the right point? Did the cycle preparation (specificity, tool config, subagent opportunities) prove useful or constraining?

**Critical framing.** The evaluator is not in the loop. By the time it runs, the cycle is done. It cannot intervene — it can only learn.

**Replaces what human did.** The human reviewing the session at the end, deciding what worked.

### 2.6 Memory system

Split into four distinct stores.

**Episodic memory** — "what happened." Raw event log: goal, plan, actions, trigger fires, brain verdicts, steward interventions, results, score, seeder reflection. Append-only.

**Semantic memory** — "what is generally true." Facts about the world distilled from episodic data.

**Strategy memory** — "what worked before." Reusable plan templates indexed by goal type and success rate.

**Failure memory** — "what broke the system." Catalogued errors with attribution.

**Write access.** Only the evaluator writes. Everyone else reads.

**Exception for Decision Reports (v1.1).** Components emit Decision Reports as structured output (section 2.8), but reports do NOT bypass the write-gating rule — they accumulate in a per-Run buffer and the evaluator drains the buffer at cycle close, persisting validated reports to memory. The only direct-write case is evaluator self-reports (`self_reported=true`), which the evaluator writes directly because routing through itself is impossible by construction.

### 2.7 Context steward (continuous monitor)

**Function.** Continuously tracks framework context state during cycle execution. Intervenes when context quality is at risk. Runs in parallel with the framework throughout each cycle; goes quiet when context is healthy.

**Operational model (mechanism corrected v1.3).** Distinct from all other components. The triage gate fires once per request. The seeder fires at cycle boundaries. The steering brain fires on triggers. The evaluator fires once per cycle close. **The context steward fires on every tool call**, via CC's `PostToolUse` hook — the finest grain CC exposes to an external observer. The earlier framing ("runs continuously, catches degradation mid-thought, mid-reasoning") was aspirational; CC offers no live mid-turn context API, so the real cadence is per-tool-call. In a turn of 15–20 tool calls this is frequent enough to track context growth and intervene before CC's own autocompact fires.

The steward is still its own component (it meets Principle 1's bar: distinct cadence, distinct cost profile, non-foldable), but it is realized as a sequence of short `PostToolUse` hook invocations updating an orchestrator-owned token counter, not as a separate process polling CC.

**Inputs.**
- Framework's current context state (utilization percentage, recent additions, accumulated history)
- Original goal and current cycle direction (to judge what's relevant)
- The current cycle's progress

**Outputs (when intervening).**

- `suggest_compact(preserve_guidance)` — proactive compact with instructions about what to keep. Used when context is filling but the cycle has clear retention priorities (goal, recent decisions) and clear summarizable content (old tool results, exploration that didn't pan out).
- `suggest_clear(reason)` — clear because context is contaminated by work no longer relevant to current direction. Rare; usually only when the framework has drifted significantly mid-cycle.
- `suggest_delegate(scope)` — current sub-task should run in a fresh subagent. Used when the framework is about to do bounded research or investigation that doesn't need to pollute main context.
- `suggest_interrupt(reason)` — close this cycle early. Used when context has degraded to the point where continuing the cycle would produce low-quality work; better to return to the seeder for a fresh start.
- Silent — most of the time.

**How the framework receives suggestions.** Suggestions are not commands. They arrive as messages the framework reads, similar to how the steering brain's verdicts arrive. A `suggest_compact` reads to the framework like the user running `/compact` with guidance. The framework executes the suggestion. The framework may also receive a brain intervention that overrides a steward suggestion in narrow cases (brain has more context about current decisions; can refuse a compact that would lose state needed for an upcoming action).

**Authority.**
- Can suggest any of the four actions
- Cannot halt the framework outright (that's the brain's job on action triggers)
- Cannot generate goals (seeder's job)
- Cannot write to memory (evaluator's job)
- Suggestions are advisory in the architectural sense — the framework follows them, but the steward isn't replacing framework reasoning, it's surfacing context-management information the framework wouldn't otherwise consider

**The steward and the framework's own context tools.** The framework already has native context management (auto-compact at limits, slash commands available to a human user). The steward sits *between* the human-role and the framework's internal tools — it makes the decisions a human would make about *when* to invoke these tools, with what guidance. This is parallel to how the steering brain works: the framework has its own pause behavior, and the brain intercepts the moments where a human would have made a decision. The steward similarly intercepts the moments where a human would have noticed context state and acted on it.

**Coordination with CC's compaction (new in v1.0).** Claude Code has its own internal compaction machinery: `microCompact` runs every turn truncating large tool outputs; `autoCompact` fires at a token threshold (approximately 80% of context window, with a 13,000-token buffer reserved for the summary itself). The steward must coordinate with these, not duplicate them.

Rule: **steward intervenes before CC's autocompact would fire, never after.** Concretely, the steward's `suggest_compact` threshold sits at ~60% of *our counted tokens*. Because our estimate undercounts (we don't see CC's hidden system prompt, internal tool schemas, or framework scratchpad overhead), 60% of our count typically corresponds to 70–75% of CC's actual count — still comfortably below CC's autocompact trigger. The steward thus acts first when it's going to act at all, applying guided compaction with preservation hints, rather than letting CC's silent autocompact strip information without judgment.

The 60% / 80% relationship is a v1 build-time constant pair (tunable per deployment). If CC's autocompact fires anyway (steward missed it, threshold drifted, run exceeded estimates), the steward's other interventions — `suggest_delegate`, `suggest_interrupt` — remain orthogonal to autocompact and continue functioning. Only `suggest_compact` is at risk of double-firing with CC, and the threshold gap is the mitigation.

**Implementation note (mechanism, v1.3).** The four interventions map to real CC mechanisms (full detail in section 2.9): `suggest_compact` = the `PostToolUse` handler returns preservation guidance as injected `additionalContext` so CC self-summarizes in-turn, backed by a `PreCompact` hook that supplies the same guidance to CC's own autocompact; `suggest_delegate` = `additionalContext` suggesting CC spawn a subagent (Task tool) for upcoming bounded work; `suggest_interrupt` = best-effort, the handler sets an interrupt flag that the next `PreToolUse` hook reads and denies, ending the cycle at the next tool boundary (true mid-turn interruption is not possible); routine pings = a counter update plus a minimal Decision Report, no CC-visible action. The threshold/nuance split (rules for the 60% line, a small LLM for "is this exploration core or pollution") still applies, evaluated inside the handler.

**Cost note.** The only component that runs continuously. Cost matters more here than for other components. Should be the smallest viable model (Haiku-tier in v1 reference). Invoked periodically (every N framework steps, or every M seconds, or hook-based on context state changes) rather than per-token.

**Recording for the evaluator.** Every steward intervention is logged in episodic memory: what triggered it, what action was suggested, whether the framework followed it, what the downstream effect was. The evaluator uses this to tune intervention thresholds and identify steward errors (FM-15).

**Replaces what human did.** The human running `/context` to check state, deciding when to `/compact`, deciding when to `/clear`, deciding when to spawn subagents for context-saving purposes. The course's whole "context management" topic is what this component does.

### 2.8 Decision Reports

**Function.** Every component that makes a decision emits a structured Decision Report documenting *what was decided, what alternatives were considered, what evidence was used, and what the confidence and reversibility look like*. Reports are byproducts of the same reasoning pass that produced the decision — not a separate analytical step.

**Why this exists.** Event logs ("brain returned proceed at T") tell you *what happened*. Decision Reports tell you *why and what else was on the table*. Production AI systems need both. Without structured decision reasoning, post-hoc analysis depends on replaying the system; with reports, an auditor can scan reasoning across runs without re-executing anything.

**Operational model.** Each component generates its own reports as structured output. Reports do NOT write directly to memory — they go to a per-Run report buffer (in-memory queue keyed by `run_id`). The evaluator drains the buffer at cycle close, validates each report against its component's schema, and persists to memory. This preserves the v0.9 rule that only the evaluator writes (section 2.6), while enabling every component to participate in the audit substrate.

**The one exception: evaluator self-reports.** The evaluator's own decisions (scoring, attribution, threshold tuning) cannot route through itself — a notary can't notarize their own signature. Evaluator reports write directly to memory, but are flagged `self_reported=true` so external audits know to apply extra scrutiny. This is the only case where the evaluator-mediated-writes rule is bypassed.

**Schema.** All reports share a common skeleton with component-specific extensions.

```yaml
report_id: <uuid>
run_id: <run uuid>
cycle_id: <which cycle in the run>
turn_id: <which CC turn>
component: triage | seeder | brain | steward | router | evaluator
timestamp: <iso>
decision_type: <component-specific enum>
report_minimal: <bool>     # true for steward routine pings; minimizes schema requirements
inputs:
  trigger: <what caused this decision to be made>
  evidence_consulted: [<list of evidence items with sources>]
  prior_context: <relevant memory retrievals>
alternatives_considered:
  - option: <name>
    weight: <0..1 or 'rejected'>
    rationale: <one sentence>
selected:
  option: <name>
  rationale: <reasoning chain>
  confidence: low | medium | high
  reversibility: low | medium | high
audit_flags:
  - <flag>: <reason>     # e.g. low_confidence_high_impact, novel_situation, conflict_with_prior
self_reported: <bool>    # true only for evaluator self-reports
component_specific:
  <fields specific to this decision type>
```

**Per-component `component_specific` blocks:**

- **Triage gate**: `route_selected`, `simple_handle_path` (if route=simple), `rejection_reason` (if route=reject), `clarification_request` (if route=reject)
- **Seeder**: `lenses_chosen`, `lenses_skipped_with_reason`, `lens_outputs`, `synthesis_weighting`, `stop_check_result`, `cycle_prep` (when continuing), `refinement_depth` (cycle count in this run)
- **Brain**: `trigger_type` (proactive_doubt | reactive_doubt | action_pattern), `triple_check_fired` (bool), `web_search_queries` (list, when fired), `pass_1_output`, `pass_2_critique`, `pass_3_reconciliation` (last three only when triple-check fired)
- **Stop-hook router**: `stage_reached` (1 | 2 | 3), `rule_match_pattern` (when stage 1), `haiku_classification` (when stage 2), `final_routing` (evaluator | brain)
- **Steward (routine ping, `report_minimal=true`)**: `counted_tokens`, `threshold_distance`, `decision: continue_silent`. Other schema fields empty by design.
- **Steward (intervention)**: `intervention_type` (compact | clear | delegate | interrupt), `framework_followed` (bool), `downstream_effect` (filled in post-hoc by evaluator)
- **Evaluator (self-report)**: `cycle_score`, `criteria_breakdown`, `failure_attribution` (when applicable), `anomaly_detected` (bool), `layer2_attribution_fired` (bool), `layer3_classifier_updated` (bool), `threshold_adjustments` (list)

**Two-tier reporting for the steward.** The steward runs continuously and would generate hundreds of reports per cycle if every check produced a full schema entry. Two tiers solve this:

1. **Routine pings** (`report_minimal=true`): emitted on every check, contain only essential fields. ~50 tokens each. Effectively structured log entries that still use the report schema so the evaluator can scan them uniformly.
2. **Intervention reports** (`report_minimal=false`): emitted only when the steward acts (compact/clear/delegate/interrupt). Full schema with alternatives, evidence, reversibility. ~600 tokens each.

Evaluator's schema validator applies lighter checks to minimal reports.

**Buffer crash behavior.** If the system crashes mid-cycle, reports in the buffer are lost. Accept this for v1: reports are reasoning audit, not transactional state. Losing a buffer means losing visibility into one cycle's decisions, not losing the cycle's actual deliverable. Operators concerned about audit completeness can configure periodic buffer flushes (every N reports or every M seconds); this is a deployment knob, not core architecture.

**Retention policy (v1 default, tunable).** Decision reports accumulate fast. Estimated ~10,500 tokens per Run on average; over a year of moderate operation, this becomes millions of tokens of audit material. v1 retention:

- Full reports (triage, seeder, brain, router, evaluator, steward interventions): retained indefinitely
- Steward routine pings: retained for 30 days, then summarized into per-cycle aggregates ("47 pings, max counted_tokens 142k, threshold never crossed") and individual pings purged
- Aggregate summaries: retained indefinitely

Operators can override either dimension. The retention policy is config, not architecture.

**Query interface (deployer-specified).** Reports must be queryable, not just storable. "What did the brain decide about destructive actions in the last month?" should be answerable without replaying any run. v1 ships with structured storage (TBD-4 memory architecture) supporting these query shapes:

- Filter by component, decision_type, time window, audit_flag
- Filter by confidence/reversibility (find low-confidence high-impact decisions)
- Filter by `self_reported=true` (find evaluator self-audits needing external review)
- Cross-reference: "show all brain reports where triple_check_fired and the next cycle scored below threshold"

The UI for these queries (CLI, dashboard, notebook integration, scheduled summaries) is deployment-specific (TBD-8a).

**Schema evolution.** Lock the spine, iterate the ribs. The top-level skeleton (report_id, run_id, component, inputs, alternatives, selected, audit_flags) is stable. `component_specific` blocks are explicitly evolvable — fields can be added across versions without breaking older reports. The evaluator's schema validator is version-aware.

**Replaces what human did.** The human writing post-mortem notes after each AI session: "the agent chose X, considered Y and Z, picked X because [reasoning], I disagreed but let it run." Decision reports are that note, generated by the components themselves, in a form that aggregates across many runs.

### 2.9 Integration surface — how the wrapper attaches to Claude Code

This section is new in v1.3. It exists because the v1.0–v1.2 dispatch design described mechanisms that do not map to Claude Code's real extension points (a hook firing on a mid-turn magic string; an external process compacting CC mid-turn; "continuous" context monitoring). v1.3 re-grounds every wrapper–CC interaction on the two mechanisms CC actually provides: **hooks** and **MCP tools**.

**The orchestrator process.** A single long-lived process (`core/orchestrator.py`) is the spine. It runs the triage gate, spawns and manages CC sessions (one per Run), and owns all persistent state: the memory DB connection, the per-Run Decision Report buffer, the steward's token-counter state, the dispatch lock, and the interrupt flag. It hosts the brain, seeder, steward logic, and evaluator as in-process modules. It exposes a local IPC endpoint (Unix socket / named pipe / localhost TCP) that the hook handlers and the MCP server call into. **All judgment lives in the orchestrator; the hooks and the MCP tool are thin plumbing that forward a CC event and translate the orchestrator's decision back into the response CC expects.**

**Proactive brain entry — the `consult_director` MCP tool.** The wrapper ships a small MCP server exposing one tool, `consult_director(question, context)`. The `SessionStart` instruction tells CC to call it instead of asking the user. CC calls it mid-turn, the call blocks (MCP calls are synchronous), the orchestrator runs the brain, and the verdict returns as the tool result. CC reads it and continues — no halt, no turn boundary. This is the common case and is why the proactive path is cheap.

**Reactive brain entry + evaluator entry — the `Stop` hook.** Fires at the end of every turn. The handler reads the final assistant message and runs the Stop-hook router (rules → Haiku → default-to-completion). If the message is a halt (CC asked the user instead of calling the tool), the handler invokes the brain and returns `{"decision": "block", "reason": "<verdict>"}`; CC's native semantics inject the reason and continue the **same** session. If it is a genuine completion, the handler returns nothing and the orchestrator routes the turn to the evaluator, then the seeder. (No `UserPromptSubmit` is synthesized to resume — block-and-continue is the native mechanism.)

**Action-pattern brain entry — the `PreToolUse` hook.** Fires before each tool call. The handler matches the pending call against the four registered action patterns (`git_push_to_public_repo`, `claim_done`, `add_dependency`, `modify_schema`). On a match it invokes the brain and maps the verdict to PreToolUse semantics: `proceed` → allow, `redirect` → allow with injected `additionalContext` pointing at the context to re-read, `halt` → deny with reason. On no match it allows immediately.

**Context steward — the `PostToolUse` + `PreCompact` hooks.** The `PostToolUse` handler fires after each tool call, updates the orchestrator-owned token counter (tool-result size + running total), and evaluates the 60% threshold. Interventions: `suggest_compact` returns preservation guidance as injected `additionalContext` (CC self-summarizes in-turn); a `PreCompact` hook supplies the same guidance to CC's own autocompact as a safety net; `suggest_delegate` injects a suggestion to spawn a subagent; `suggest_interrupt` sets an interrupt flag that the next `PreToolUse` hook reads and denies, ending the cycle at the next tool boundary. Granularity is per-tool-call, not mid-thought.

**`SessionStart` hook.** Fires when the orchestrator opens a session for a Run. Injects the `consult_director` instruction and any standing deployment rules.

**State across hook invocations.** Each hook invocation is a fresh OS process, so anything that must survive between calls lives in orchestrator-owned state reached over IPC (or, for the simplest v1, small per-Run JSON state files the handlers read/write): the token counter, the dispatch lock, the interrupt flag, the report buffer. No hook holds durable state in its own memory.

**Concurrency / memory-access model (resolves the audit's concurrency hole).** Because the steward is a sequence of short hook invocations rather than a separate polling process, and because Decision Reports accumulate in the orchestrator's in-memory buffer rather than being written by each component, **the memory DB has exactly one writer: the evaluator, running single-threaded at cycle close inside the orchestrator.** Readers (brain, seeder) query through the orchestrator's single owned connection. Hook handlers never open the DB directly — they talk to the orchestrator over IPC. With no cross-process SQLite access, the WAL-vs-DELETE journaling question that bit earlier projects on bind mounts does not arise; v1 uses one connection owned by the orchestrator. (This is the deliberate fix for the "continuous parallel steward + SQLite" contention the audit flagged.)

**External dependencies (pinned in v1.3).**

- **The Prompt.** The seeder, brain Layer 6, and triage Stage 3 invoke The Prompt (the-prompt-to-rule-them-all). For v1 it is **vendored** into the repo at a pinned commit (`vendor/the-prompt/PROMPT.md`), not referenced externally, so the build is reproducible. Invocation (`core/prompt/invoke.py`): load the vendored text, prepend it as the system prompt, call the Anthropic API — Sonnet for routine seeder/triage use, Opus for Layer 6 triple-check. Updating the vendored copy is a deliberate, version-bumped action.
- **Web search backend.** Components that "use web search" (brain Layer 6 Pass 2, seeder comparative lens, triage Stage 3) call a pluggable interface (`core/search/backend.py`), never a hardcoded provider. v1 default is the deployer's available search. In internet-restricted environments the backend routes through a local proxy (e.g., a proxy MCP) — the expected configuration on the reference build machine.

**What is NOT assumed.** No ability to read CC's live token state mid-turn (only per-tool-call estimates). No ability to force a `/compact` inside a running turn (only injected guidance + the PreCompact safety net). No hook that fires on arbitrary model text mid-turn (the MCP tool replaces that need). No second concurrent writer to memory. If a future CC version adds richer surfaces, the wrapper can use them, but v1 depends only on what is listed here.

## 3. Data flow

Each request goes through the triage gate first; loop-worthy requests then proceed through cycles bounded by the seeder's reflections, with the context steward monitoring throughout.

**Request intake.**
0. **Triage gate** receives the raw request from the goal source. Classifies:
   - Loop-worthy → continue to step 1
   - Simple lookup → handle directly, return result, end
   - Reject → return clarification request to goal source, end

The triage decision is logged regardless of route.

**Cycle 0 (cold start).**
1. **Seeder cold-start.** Pass-through with default cycle preparation if configured. The validated goal is handed to the framework. No reflection.
2. **Cycle wrapper applies cycle preparation** (MCP enable/disable, etc.) before starting framework session.
3. **Framework decomposes goal into a plan.**
4. **Framework begins action sequence.**
   - 4a. For each action, check action-pattern triggers.
     - Match → **steering brain fires (trigger type 2)** → verdict → framework proceeds/redirects/halts
     - No match → action proceeds
   - 4b. If the framework would have asked the user a question, it calls the `consult_director` MCP tool instead (proactive path).
     - **Steering brain fires (trigger type 1)** → verdict returns as the tool result → framework continues in-turn. (If CC instead just asks, the `Stop` hook catches it reactively — trigger type 2.)
   - 4c. Actions hit the external world; results, errors, state changes come back.

**Throughout the cycle (parallel track).**
- **Context steward monitors framework context state continuously.** When intervention is warranted, emits suggest_compact/clear/delegate/interrupt. Framework executes the suggestion. Each intervention logged for evaluator review.

5. **Cycle ends** — either by successful completion, by brain `halt`, by steward `suggest_interrupt` being followed, or by external failure.

**Cycle close.**
6. **Evaluator runs.** Scores cycle 0. Attributes failures. Adjusts trigger set, brain priors, triage classifier weights, steward intervention thresholds. Consolidates memory.
7. **Memory updated.** Episodic event recorded, including all steward interventions and their outcomes.

**Cycle boundary — seeder reflection + preparation.**
8. **Seeder runs multi-lens reflection.** Selects relevant lenses for the cycle 0 deliverable. Each lens produces a perspective. Synthesizes:
   - If a clear direction emerges → generates goal for cycle 1 **plus cycle preparation** (specificity, tool config, subagent opportunities). Loop returns to step 2 with that goal and config.
   - If skeptical lens dominates or no compelling direction → emits `no_next_goal` with reason code. Session ends.

**Subsequent cycles.**

Cycles 1, 2, 3... each follow the same shape: cycle wrapper applies preparation, framework executes with steward monitoring, evaluator scores, memory updates, seeder reflects at boundary. Each boundary may end the session or generate the next cycle's goal+preparation.

Note: most sessions are 2 cycles (build + refine) followed by `refinement_complete`. Some are 1 cycle if no refinement is warranted.

## 4. Key design insight

This system is not "two LLMs plus morality" and it is not "an LLM in a loop with a critic." It is a self-updating control system that wraps an existing agentic framework with infrastructure replacing the human roles around it.

The seeder, steering brain, context steward, evaluator, and triage gate are control surfaces with bounded jobs. Each one's authority is constrained by what it can and cannot read, write, halt, or generate. Each operates on its own temporal model — once per request (triage), at cycle boundaries (seeder), on triggers (brain), continuously (steward), or once per cycle close (evaluator). Treating any of them as a general-purpose autonomous agent breaks the design.

The framework (Claude Code) does the cognitive work. We do the wrapping.

## 5. Design principles

Principles that emerged across the v0.1 → v0.9 design conversations. These are load-bearing for future work on this project.

**Principle 1: Prefer prompt-level instructions over new components.**

When a new component is proposed, the first question to ask is "could this be a prompt-level instruction inside an existing component instead?" Most of the time the answer is yes. The architecture has collapsed multiple proposed components (the three-component steering layer, the completion gate, the preprocessor) back into prompts inside existing components when the proposed mechanism didn't require separation.

**Exception.** A new component is warranted when the responsibility has a structurally different operational model (continuous vs event-driven), a different reasoning surface, a different cost profile, or cannot be folded without distorting existing components. The context steward (v0.9) met all four tests; this is the test case for when a new component passes the bar.

**Principle 2: Structure-by-mechanism, not structure-by-intention.**

Claiming a design "terminates by construction" or "handles X correctly" requires the mechanism to actually enforce the property, not just intend it. The dispatch lock for Layer 6 recursion is a concrete bit of state; without it, recursion is unbounded regardless of design intent. Several iterations of this conversation surfaced cases where intended properties weren't backed by mechanism — these are recorded in the changelog so the pattern can be watched in future work.

**Principle 3: The system replaces the human who uses the framework, not the framework itself.**

The synthetic-user project does not reinvent agentic loops. Claude Code (or any equivalent) does that work. The project's scope is the infrastructure around the framework — the wrapper, the substitutes for the human roles that ordinarily sit outside the loop. This cut clarifies scope, prevents reinventing what already works, and keeps the project focused on what's genuinely new.

**Principle 4: Find the natural threshold the work implies, then put your mechanism there.**

Mechanisms should align with boundaries the work itself produces, not with arbitrary thresholds. The natural triage boundary is between asking and acting. The natural stop boundary is after refinement, not after build. The natural intervention boundary is at action patterns the human would have noticed. The natural learning boundary is post-cycle, not in-cycle. The natural context-management boundary is continuous, not event-driven. Each of these was discovered by asking "is this really how it needs to work, or is this structure I'm adding?"

**Principle 5: Trust the loop; don't pre-empt reality.**

The architecture has multiple moments where a halt-on-doubt mechanism was proposed and rejected. The Layer 6 triple-check returns its best guess and lets reality validate post-hoc. The seeder's stop decision is earned through multi-lens reflection, not gated by a counter. The synthetic-user hypothesis is that closed loops stabilize through reality's disagreement, not through cautious abstention.

**Principle 6 (new in v0.9, extended in v1.2): Build quality into the process, don't inspect it in afterward.**

(Deming.) The architecture's design choices reflect this consistently. The seeder's cycle preparation (specificity, tool config, subagent identification) builds context efficiency into the cycle's start rather than letting context problems emerge for the steward to fix mid-cycle. The triage gate builds work-fitness into the entry rather than letting the engine process unfit work. The action-pattern triggers build irreversibility caution into action moments rather than catching mistakes afterward. The principle that ties these together: when quality can be designed into a phase, prefer that over hoping later phases will correct for upstream variance.

**Operational corollary (locked in v1.2): acceptance tests are upstream of code.** The implementation strategy (section 10) operationalizes this principle directly. Acceptance test scenarios are written before code, the walking skeleton passes scenarios in order of difficulty, and every component grows under test pressure rather than being unit-built and integrated later. This is the testing equivalent of designing quality in: the test defines what "done" means before the code is written, rather than being applied retroactively to confirm that existing code happens to work. The contract-test layer for inter-component interfaces and the targeted unit-test layer for deterministic gnarly logic are defense-in-depth around the acceptance-driven core.

## 6. Failure modes

The most important section. These are the predictable ways the system fails.

### Failure mode 1: Seeder drift (formerly "synthetic user drift")

**Symptom.** Goals become abstract over time. The system stops doing useful work.

**Cause.** The seeder's reflection produces directions disconnected from external usefulness.

**Mitigation.** Multi-lens reflection forces multiple perspectives. Skeptical lens explicitly argues for stopping when no compelling direction emerges. Evaluator audits seeder direction quality.

### Failure mode 2: Echo loop collapse

**Symptom.** Components reinforce each other. Output becomes increasingly coherent and increasingly wrong.

**Cause.** Missing external negative feedback.

**Mitigation.** The external world is the anti-collapse layer. Mandatory tool execution validation.

### Failure mode 3: Reward hacking (evaluator gaming)

**Symptom.** Reported reliability rises while actual reliability falls.

**Cause.** Classic Goodhart.

**Mitigation.** Hidden metrics. Randomized audits. Multiple uncorrelated signals. Seeder's multi-lens reflection as independent check.

### Failure mode 4: Memory contamination

**Symptom.** Bad outputs become "truth" in memory.

**Cause.** Memory accepts writes without confidence weighting.

**Mitigation.** Only the evaluator writes. Confidence scoring. Decay for unverified memory.

### Failure mode 5: Goal instability

**Symptom.** No long-term project ever completes.

**Cause.** Goal generation has no persistence pressure.

**Mitigation.** Seeder's reflection considers session history. Evaluator penalizes task abandonment.

### Failure mode 6: Tool misgeneralization

**Symptom.** The framework assumes tools behave reliably in unseen contexts.

**Cause.** Tool reliability is learned from a narrow distribution.

**Mitigation.** Sandboxed execution. Action-pattern triggers. Tool-specific validators.

### Failure mode 7: Brain rubber-stamping

**Symptom.** Steering brain consistently returns `proceed` on triggered situations that should have been halted.

**Cause.** Brain's resolution priors drift toward leniency.

**Mitigation.** Evaluator audits brain verdicts. Random sampling for human review during early operation.

### Failure mode 8: Seeder–evaluator collusion

**Symptom.** Seeder's reflection consistently aligns with the evaluator's scores.

**Cause.** Same model, same prompt heuristics.

**Mitigation.** Different model for seeder vs evaluator. Multi-lens reflection forces stances the evaluator doesn't use.

### Failure mode 9: Layer 6 amplification

**Symptom.** The brain triple-checks itself, produces confident-sounding answer with shared blind spots.

**Cause.** Self-critique within a single model has shared priors.

**Mitigation.** Different models for the three passes. Web search on Pass 2.

### Failure mode 10: Recursive Layer 6 amplification

**Symptom.** A single trigger produces exponentially many Prompt invocations.

**Cause.** The Prompt has no memory of being invoked inside another invocation.

**Mitigation.** The dispatch layer's binary `in_triple_check` lock prevents nested triple-checks. **As of v1.0, the lock is also shared with the Stop-hook router** — a brain dispatch initiated by the Stop hook sets the lock, the seeder's next `UserPromptSubmit` checks it and suppresses redundant reflection. Same bit of state; two entry points reading it.

### Failure mode 11: Premature session completion

**Symptom.** The seeder emits `no_next_goal` after cycle 0, shipping the rough first-build version.

**Cause.** The skeptical lens dominates too easily.

**Mitigation.** Lens selection biases toward including production and creative lenses on first-build cycles.

### Failure mode 12: Stop-avoidance drift

**Symptom.** The seeder fails to emit `no_next_goal` even when work is done.

**Cause.** Over-correction during prompt tuning.

**Mitigation.** Skeptical lens explicitly checks session history. Sessions exceeding 3 cycles get a yellow flag.

### Failure mode 13: Lens collapse to single perspective

**Symptom.** The seeder runs multi-lens reflection but one lens dominates the synthesis.

**Cause.** One lens consistently produces the most concrete suggestions.

**Mitigation.** Prompt requires named contribution from each chosen lens before synthesis.

### Failure mode 14 (new in v0.9): Silent context degradation

**Symptom.** The framework auto-compacts context to stay within limits, losing detail that mattered. Reasoning quality drops late in long sessions.

**Cause.** Without the context steward, context management is invisible to all wrapper components. Auto-compaction happens silently with no human-equivalent judgment about what to preserve.

**Mitigation.**
- Context steward runs continuously, intervenes before the framework auto-compacts
- Steward's `suggest_compact` includes preservation guidance, unlike silent auto-compact
- Evaluator tracks context state at cycle close; cycles that completed near the context limit get flagged

### Failure mode 15 (new in v0.9): Steward over-intervention

**Symptom.** The context steward intervenes too aggressively — compacting context that should have been preserved, clearing context that contained important state, delegating work that should have run in the main context. The framework loses information the steward judged unimportant but the cycle actually needed.

**Cause.** Steward's heuristics for "what's relevant" are imperfect. False positives lead to interventions that hurt cycle quality.

**Mitigation.**
- Evaluator audits steward interventions against cycle outcomes
- Steward suggestions can be overridden by the steering brain in narrow cases (brain has more context about upcoming actions)
- Conservative defaults — steward errs toward letting the framework run with full context

### Failure mode 16 (new in v0.9): Over-preparation drift

**Symptom.** The seeder's cycle preparation becomes too prescriptive — overly specific task prompts that constrain the framework into the seeder's narrow conception when the framework's own approach would have been better.

**Cause.** The seeder's "be specific" instinct produces prompts so detailed they remove framework latitude.

**Mitigation.**
- Seeder's preparation focuses on *what to address* (specific gaps, specific opportunities) rather than *how to approach* (specific implementations, specific algorithms)
- Evaluator audits whether specificity helped or constrained
- Preparation suggestions can be relaxed by the steering brain if the framework needs more latitude

### Failure mode 17 (new in v1.1): Decision Report inflation / audit noise

**Symptom.** Reports accumulate faster than they can be reviewed. Steward routine pings dominate storage. Audits become slow because filtering is needed before any pattern can surface. Operators stop reading reports because the signal-to-noise ratio is poor.

**Cause.** Continuous-monitor components (steward) emit reports proportional to runtime, not to decision count. Without aggregation, the audit substrate buries genuine decisions in routine noise.

**Mitigation.**
- Two-tier reporting (routine pings minimal, interventions full) keeps full-schema reports proportional to real decisions
- 30-day rolling summarization for steward routine pings prevents indefinite accumulation
- Query interface biases toward full reports (minimal pings filtered out unless explicitly requested)
- Evaluator audits the audit substrate itself: if reports stop being read, that's a finding

### Failure mode 18 (new in v1.3): Dispatch escape

**Symptom.** CC neither calls `consult_director` nor emits halt-language the Stop-hook router can detect — it makes a consequential assumption silently and proceeds, and the router classifies the turn as a clean completion.

**Cause.** The proactive SessionStart instruction faded under context compression AND the implicit halt was phrased so it didn't match the router's rule/Haiku patterns. Both layers of the hybrid missed the same event.

**Mitigation.**
- The evaluator's post-hoc audit flags turns where CC made a consequential, low-reversibility decision with no `consult_director` call on record; persistent escapes tighten the SessionStart instruction and the router's rule set.
- The `PreToolUse` action-pattern triggers still catch the irreversible subset (public push, dependency add, schema change, done-claim) regardless of whether CC consulted the brain — so the highest-stakes escapes are caught on a separate mechanism.
- This is the explicitly accepted residual risk of trusting the loop (Principle 5): the system tolerates silent low-stakes assumptions and relies on reality + the evaluator to surface the costly ones.

### Failure mode 19 (new in v1.3): Hook handler failure leaves CC unsupervised

**Symptom.** A hook handler crashes, times out, or the orchestrator IPC endpoint is unreachable; CC proceeds for that event with no steering, steward, router, or action-pattern coverage.

**Cause.** Hooks are external processes that can fail independently of CC. A wrapper that assumes its handlers always run would silently lose supervision exactly when something is already wrong.

**Mitigation — every handler fails safe, in the safe direction for its event:**
- `PreToolUse` crash → allow for non-action-pattern tools, **deny** for the four registered action patterns (fail closed on the irreversible set).
- `Stop` crash → let CC stop and route the turn to the evaluator (never trap CC in a blocked-stop loop).
- `PostToolUse` crash → skip the steward update for that step (lose one data point, not the cycle).
- `consult_director` unreachable → the tool returns an explicit "director unavailable, use your best judgement and note the assumption" result, which the evaluator later audits.
- Every handler failure is logged as a finding; repeated failures raise a yellow flag. The orchestrator exposes a health endpoint the handlers ping, so a dead orchestrator is detected rather than silently degrading.

## 7. What this is, restated

It bears repeating because the framing matters:

- **Not a path to AGI.** It is a control system around an existing agentic framework.
- **Not safety research.** The components optimize reliability, not alignment.
- **Not novel in any single component.** Actor-critic, self-play, reflection, tool use, persistent memory, multi-perspective evaluation, context management — all of these exist. The contribution, if any, is in the specific composition: the decomposition of "the human in the loop" into roles, the substitution of named components for the roles that need building, the inheritance of the rest from the framework.
- **Not human-in-the-loop.** A standard agentic-workflow framing positions the human as a governor reviewing the agent's plan before execution. The synthetic-user architecture deliberately rejects this. The triage gate is the only place a human can be involved, and it sits *before* the loop runs, not as a checkpoint inside it. Once the gate accepts the request, the system runs to completion without human approval at any intermediate step. Safeguards are structural (multi-lens reflection, context monitoring, external grounding, post-hoc evaluator learning) rather than procedural.
- **Not finished, but implementation-ready.** This is v1.3. All design TBDs are resolved (section 8) and the Claude Code integration mechanism is specified (section 2.9). What remains is building it against the acceptance scenarios in section 10.

## 8. Design decision history (all resolved)

Every TBD from the design phase is now resolved. This section retains the resolution record so future maintainers understand *why* each decision landed where it did. No architecture work remains.

### Genuine architecture decisions (resolved)

**TBD-1b: Seeder cycle-boundary reflection structure.** Multi-lens reflection with six potential lenses (comparative, aspirational, creative, production, skeptical, user-perspective). Stop decision emerges from skeptical lens winning the synthesis. Extended in v0.9 with cycle preparation. Locked at v0.9.

**TBD-2a: Evaluator learning mechanism.** Three-layer hybrid: rules-based scoring (Layer 1, always, cheap, deterministic), LLM attribution on anomaly only (Layer 2, Opus call when needed), classifier-based threshold tuning (Layer 3, scikit-learn on tabular features extracted from episodic memory). Resolved via research; pattern matches Skynet's RIPPER-based learned-rule quarantine. Resolved in research-findings (2026-05-18), locked at v1.2.

**TBD-2b: Steering brain implementation.** Framework's reasoning as default + The Prompt with web search as Layer 6 escalation. Triple-check pattern (Pass 1 answer → Pass 2 critique with web search → Pass 3 reconciliation), dispatch lock prevents recursion. Locked at v0.3.

**TBD-2c: Initial action-pattern trigger set.** Small custom layer over framework's own pauses. Four initial triggers locked: `before:git_push_to_public_repo`, `before:claim_done`, `before:add_dependency`, `before:modify_schema`. Locked at v1.2.

**TBD-8a: Observation surface (consumer side).** Out of architecture scope — deployer's choice (logs, dashboard, journal, scheduled summaries, notebook integration). v1.2 confirms this as a deployment decision, not architecture. Closed.

**TBD-8b: Decision Report schema specifics (producer side).** Top-level skeleton and per-component blocks locked in section 2.8. Schema versioning principle ("lock the spine, iterate the ribs") locked in v1.1. Locked at v1.1.

**TBD-9: Triage gate design.** Three-stage cascade: rules (Stage 1, ~70% of requests, <1ms, free) → Haiku classifier (Stage 2, ~28%, 200-500ms, ~$0.0001 each) → The Prompt fallback (Stage 3, ~2% ambiguous). Six initial simple-handle paths defined (weather/time/currency/fact-lookup/web-search/definition). Resolved in research-findings (2026-05-18), locked at v1.2.

**TBD-11: Context steward design.** Token estimation method: running counter of all observed I/O, conservative by construction (we undercount). Autocompact coordination: steward at ~60% of our counted tokens, before CC's autocompact at ~80% of its own count. Monitoring mechanism: hook-based subscription to CC's per-turn tool-result events; polling fallback. Intervention threshold for compact locked at 60%; other thresholds are evaluator-tunable v1 constants. Locked at v1.2.

### Configuration items (resolved)

**TBD-4: Memory architecture.** SQLite for episodic/strategy/failure tables + Chroma or FAISS for semantic memory. Custom schema beats off-the-shelf agent-memory libraries (Mem0, Letta) because our memory is system-state, not user-conversation. Schema sketched in research-findings doc. Locked at v1.2.

**TBD-5: Model selection per role.** v1.2 reference: Claude tiers across roles. Haiku for triage Stage 2 and context steward (continuous monitor, smallest viable model). Sonnet for seeder multi-lens reflection and steering brain dispatch routine cases. Opus for evaluator Layer 2 attribution and Layer 6 triple-check. Deployer can override; v1.2 ships with these defaults. Locked at v0.7.

### Closed without action (resolved)

- **TBD-1** — Cold-start goal source: out of scope. Deployer's choice (human prompt, agent queue, file backlog, autonomous generation, corpus). Closed v0.4.
- **TBD-3** — Reality injection frequency: dissolved. Per-action grounding via the framework's tool calls handles this implicitly; no separate mechanism needed. Closed v0.2.
- **TBD-6** — Task domain: closed; architecture is domain-agnostic. Whatever the framework can do, the wrapper can run cycles over. Closed v0.7.
- **TBD-7** — Run model: closed; architecture is run-model-agnostic. Continuous daemon, scheduled bursts, or interactive sessions all work. Closed v0.7.
- **TBD-10** — Completion gate: collapsed into TBD-1b. The seeder's skeptical lens IS the completion gate; no separate mechanism. Closed v0.5.

### Resolved during the v1.3 pre-implementation audit

A pre-build audit (2026-06-08) re-read the locked architecture against Claude Code's real extension surface and found eight holes. All are now resolved; the most consequential changed a core mechanism.

1. **Proactive dispatch had no real mechanism (severity: high).** v1.0–v1.2 had CC emit `[steering-director:]` mid-turn for a hook to catch — but no CC hook fires on arbitrary mid-turn text. **Resolved:** proactive dispatch is now the synchronous `consult_director` MCP tool (sections 2.2, 2.4, 2.9).
2. **Reactive resume was described two incompatible ways.** "Synthesize a follow-up `UserPromptSubmit`" vs the native Stop-hook block-and-continue. **Resolved:** standardized on `Stop` returning block-with-reason; CC continues the same session (sections 2.4, 2.9).
3. **Steward monitoring + actuation were unverified.** "Continuous mid-thought monitoring" and an external mid-turn `/compact` don't exist in CC. **Resolved:** steward is `PostToolUse`-driven (per-tool-call), `suggest_compact` injects guidance + a `PreCompact` safety net, `suggest_interrupt` resolves at the next tool boundary (sections 2.7, 2.9).
4. **Evaluation-criteria source was unspecified.** Cycle 0 had no declared criteria. **Resolved:** cycle 0 criteria come from CC's wrapper-prompted done-when declaration; cycle N>0 from seeder preparation (sections 2.1, 2.5).
5. **Run↔session mapping was circular.** **Resolved:** v1 maps exactly one Run to one CC session; cycles are consecutive turns within it (section 0).
6. **The Prompt was an unpinned external dependency.** **Resolved:** vendored at a pinned commit, invoked as a system-prompt prefix (section 2.9).
7. **Web search assumed unrestricted internet.** **Resolved:** pluggable search backend that routes through a proxy in restricted environments (section 2.9).
8. **Memory concurrency model was undefined.** **Resolved:** single-writer (evaluator) inside the orchestrator; hooks never touch the DB directly; no cross-process SQLite contention (section 2.9).

Two new failure modes were added for the re-grounded mechanism: **FM-18 (dispatch escape)** and **FM-19 (hook handler failure)**. The architecture is now at 19 failure modes.

### Summary

**Twelve design-phase TBDs plus eight v1.3 pre-implementation audit findings. All resolved. Zero architecture work remaining — the system is implementation-ready.**

The buildable architecture is sections 1-7 (concept, components, data flow, design insight, design principles, failure modes, framing). The implementation path is section 10. The audit substrate is section 2.8. Everything else is context for understanding why decisions landed where they did.

## 9. Component summary

For quick reference, the system at v1.3 consists of:

**Auxiliary (outside the loop):**
- **Triage gate** — routes incoming requests; loop / simple-handle / reject

**Engine:**
- **Seeder** — cycle-boundary multi-lens reflection + cycle preparation; generates next goal with config, or stops session
- **Executor** — inherited from the framework (Claude Code in v1)
- **Steering brain** — resolves in-flight situations (framework reasoning + Prompt escalation + dispatch wrapper)
- **Context steward** — continuous context monitoring; suggests compact/clear/delegate/interrupt as needed
- **Evaluator** — post-hoc learning; writes memory; tunes triggers, brain priors, steward thresholds, triage classifier

**Infrastructure:**
- **External world** — non-negotiable grounding (inherited from the framework's tool calls)
- **Memory** — four stores (episodic, semantic, strategy, failure), write-gated to the evaluator
- **Decision Reports** (new in v1.1) — audit substrate, every component emits structured reasoning, evaluator-mediated writes, two-tier reporting for continuous monitors

Five components we build (seeder, brain dispatch, context steward, evaluator, plus triage gate as auxiliary), plus the **orchestrator** (formerly "cycle wrapper") that hosts them all, owns persistent state, and attaches to Claude Code through hooks and the `consult_director` MCP tool (section 2.9). The executor is the framework. The world is what the framework's tools touch. Memory is configured, not built. The integration surface (hooks + one MCP tool) is the load-bearing new code that makes any of it actually run on CC.

## 10. Implementation strategy

This section is the entry point for the build phase. The architecture is locked; this section says how to build it.

### 10.1 Core principle: acceptance tests are upstream of code

The Synthetic User system is a control system with tightly coupled components. Almost every documented failure mode (FM-2, 3, 7, 8, 13, 14, 15, 16, 18, 19) is an interaction failure, not a component-internal failure. Unit-testing components in isolation would catch approximately none of these.

The implementation therefore follows **acceptance-test-driven development** at the system level. Tests are written before code. Tests define what "done" means. Components grow under test pressure rather than being built bottom-up and integrated later. This operationalizes Principle 6 (build quality into the process).

**Build sequence:**

1. **Write acceptance test scenarios** (section 10.3) before any production code exists. These ARE the specification.
2. **Build a walking skeleton.** All components present as stubs. Data flows end-to-end. Skeleton passes scenario 1 (the simplest) and only scenario 1.
3. **Iterate per scenario.** Pick the next failing scenario. Identify the component(s) that need to grow. Grow them minimally. Run *all* acceptance tests, not just the new one — a change in any component can break another's assumptions. Fix any regressions before moving on.
4. **Component depth comes from test pressure.** The seeder's multi-lens reflection grows because a scenario needs it. The brain's triple-check fires because a scenario forces it. The evaluator's classifier matures because real scoring failures demand it. Architecture does not pre-specify the full implementation of each component; tests pull capability into existence as required.

### 10.2 Test layers (defense in depth)

Three layers, listed by priority and where coverage starts:

**Layer 1 — Acceptance scenarios (primary).** End-to-end tests covering full Runs. Drives 80% of implementation work. Every scenario in section 10.3 is a Layer 1 test. Failure of a Layer 1 test blocks progress on later scenarios.

**Layer 2 — Contract tests (defense in depth on interfaces).** Schema-level tests on the stable interfaces between components: Decision Report schema, brain verdict shape, steward suggestion shape, seeder output shape, evaluator score shape. Written just-in-time when an interface is first touched in a Layer 1 test. Prevents silent contract drift as components grow internally.

**Layer 3 — Targeted unit tests (defense in depth on deterministic gnarly logic).** Reserved for the minority of code where unit-isolation actually tests something true: regex matching in the Stop-hook router, dispatch lock state machine transitions, Decision Report schema validation, idempotent patch application logic, token counter increment correctness. Not for LLM-calling components — those are tested only through acceptance scenarios where their behavior matters.

**Anti-pattern explicitly rejected: unit tests that mock the LLM.** Mocking the brain's reasoning, the seeder's lenses, or the evaluator's scoring produces tests that pass on stubs and fail on the real system. The interaction with real LLM behavior IS what's being tested; mocking it defeats the purpose. Layer 1 acceptance tests run against real models.

### 10.3 Baseline acceptance scenarios (locked at v1.2)

Fourteen scenarios. Listed in approximate order of complexity. Build order should pull scenarios in roughly this order, though later scenarios may pull capability for earlier ones forward.

**Scenario 1: Simple successful Run.** Cold-start request enters via triage. Triage routes to loop. Seeder cold-start passes the goal to CC. CC executes one turn, produces a deliverable. Evaluator scores high. Seeder reflects, all lenses converge on "done". Seeder stops with `complete`. Run terminates cleanly. Verifies: walking skeleton, data flow end-to-end, evaluator-mediated Decision Report writes.

**Scenario 2: Refinement Run.** Cold-start request requires multi-step work (e.g., "build CSV deduplicator"). Cycle 0 builds. Seeder reflects, production+skeptical lenses surface untested edge cases. Cycle 1 refines (adversarial test cases). Seeder reflects, skeptical lens dominates, stops with `refinement_complete`. Run terminates cleanly. Verifies: multi-cycle Runs, seeder multi-lens reflection, cycle preparation between cycles.

**Scenario 3: Halt-and-resume via reactive Stop-hook path.** CC halts mid-turn with disguised-as-completion language ("I need to ask..."). Stop-hook router Stage 1 catches it via regex. Routes to brain. Brain resolves. The Stop handler returns block-with-reason; CC continues in the **same session** with the brain's answer injected (no new prompt synthesized). Verifies: reactive entry point (Stop-hook block-and-continue), Stop-hook router classification, dispatch lock.

**Scenario 4: Proactive dispatch via the `consult_director` MCP tool.** CC honors the SessionStart instruction and calls `consult_director` instead of asking the user. The call blocks, the brain runs, the verdict returns as the tool result, CC continues without halting. Run completes in one turn. Verifies: proactive entry point (synchronous MCP-tool dispatch), SessionStart instruction injection, in-turn resolution with no halt.

**Scenario 5: Steward fires compact intervention mid-cycle.** Long-running cycle pushes counted tokens past 60% of context. The `PostToolUse` handler detects the crossing and returns preservation guidance as injected context; CC summarizes its working state in-turn (the `PreCompact` hook supplies the same guidance if CC's own autocompact fires first). Cycle continues healthy. Verifies: per-tool-call monitoring, token estimation accuracy, steward intervention path, autocompact-coordination threshold gap.

**Scenario 6: Triage rejection.** Malformed request enters (vague, missing context, contradictory constraints). Triage Stage 1 rules don't match, Stage 2 Haiku classifies as reject-with-clarification. Triage returns structured clarification request to goal source. No cycle ever starts. Verifies: triage rejection path, Stage 2 escalation, structured rejection format.

**Scenario 7: Triple-check fires on hard call.** Cycle hits a genuinely ambiguous decision (e.g., "should this destructive operation proceed despite low confidence"). Brain's dispatch wrapper sets `in_triple_check`. Pass 1 produces an answer. Pass 2 critiques with web search. Pass 3 reconciles. Final verdict returned to CC. Dispatch lock prevents nested triple-checks during Passes 1-3. Verifies: Layer 6 sovereignty mechanism, dispatch lock under fire, web search integration.

**Scenario 8: Evaluator catches anomaly, Layer 2 attribution fires.** Cycle completes but evaluator Layer 1 rules score below threshold. Layer 2 Opus attribution call fires, identifies the failing subsystem (e.g., "brain rubber-stamped a halt that should have been escalated"). Layer 3 classifier updates threshold weights. Failure flagged in episodic memory for future audit. Run continues to next cycle informed by the attribution. Verifies: three-layer evaluator hybrid, anomaly detection, attribution writing to failure memory.

**Scenario 9: Decision Reports queryable end-to-end.** Run a representative scenario. Query the report store afterwards: "show all brain reports from this Run where triple_check_fired". Verify the returned reports match the runtime decisions, schema-validate, are flagged correctly. Verifies: report buffer flow, evaluator schema validation, query interface, schema completeness.

**Scenario 10: Dispatch lock prevents double-fire.** Construct a Run where both the proactive SessionStart path and the reactive Stop-hook path could fire on the same logical halt (e.g., CC partially honors the SessionStart instruction but emits halt-language anyway at turn end). Verify: only one brain dispatch occurs, the dispatch lock state is shared between the Stop-hook router and the seeder's reflection path, the seeder skips reflection for the locked boundary. Verifies: FM-10 mitigation, shared lock state, no double-firing.

**Scenario 11: Long-Run survival.** Run a Synthetic User Run that spans 5+ cycles (multi-stage refinement, e.g., "design and implement a small system with tests and docs"). Steward maintains context health across the full Run via multiple compact interventions. No catastrophic context loss. No silent autocompact firing. Final cycle scores match or exceed earlier cycles. Verifies: steward sustained operation, multi-cycle stability, FM-14 mitigation in practice.

**Scenario 12: Graceful degradation under component failure.** Inject a fault into one component (e.g., evaluator's Layer 2 Opus call returns malformed output, or steward's token counter desyncs from reality). Verify: evaluator audits the fault, system continues completing the current Run without that component's full participation, fault is logged for next-Run review, and the system re-enables the component cleanly for the next Run if the fault was transient. Verifies: graceful degradation, evaluator's audit-the-audit-substrate behavior (FM-17 mitigation), no single-component failure cascades to system failure.

**Scenario 13: Dispatch escape is caught post-hoc (FM-18).** Force a Run where CC neither calls `consult_director` nor emits detectable halt-language, but makes a consequential assumption (e.g., silently picks a data format the spec left open). The turn classifies as completion. Verify: the evaluator's audit flags the unconsulted consequential decision, records it to failure memory, and (for the irreversible subset) the `PreToolUse` action-pattern path would still have fired independently. Verifies: FM-18 mitigation, evaluator post-hoc dispatch-escape detection, action-pattern independence.

**Scenario 14: Hook handler failure fails safe (FM-19).** Inject a fault into each hook handler in turn (crash / timeout / orchestrator IPC down). Verify the safe-direction default for each: `PreToolUse` denies the registered action patterns but allows ordinary tools; `Stop` lets CC stop and routes to the evaluator; `PostToolUse` skips one steward update without aborting the cycle; `consult_director` returns the explicit "director unavailable" result. Verify every failure is logged as a finding. Verifies: FM-19 mitigation, fail-safe handler behavior, orchestrator health detection.

### 10.4 Build order

Scenarios 1-2 establish the walking skeleton and basic Run lifecycle. These are the gates: nothing else gets built until scenarios 1 and 2 pass cleanly. After that, prioritize scenarios that exercise infrastructure (3, 4, 9 — hooks, dispatch, reports) before scenarios that exercise depth (5, 7, 8, 11 — steward, triple-check, evaluator, long-Run). Scenarios 13–14 (integration-surface robustness) precede the final pair; scenario 12 remains last because graceful-degradation testing requires all other components to be mature enough to fault meaningfully.

**Recommended order:** 1 → 2 → 3 → 4 → 6 → 9 → 10 → 5 → 7 → 8 → 13 → 14 → 11 → 12. (Scenarios 13–14 test the v1.3 integration surface's robustness — dispatch escape and hook-failure fail-safes — and slot in before the long-run and graceful-degradation tests.)

Each scenario should fail meaningfully before code is written to pass it. "Meaningfully" means: the test exists, the system runs against the test, the test reports a specific failure that identifies what's missing. Tests that fail because of missing-import errors or syntax errors don't count — those indicate the scaffolding isn't ready yet, not that the test is providing pressure.

### 10.5 What this section is NOT

- Not a deployment guide. Deployment specifics (model selection, observation UI, memory backend, cold-start source) are deployer decisions, not implementation-strategy decisions.
- Not a project schedule. No time estimates, no team-sizing, no Gantt chart. The acceptance scenarios drive the schedule; whoever builds this should estimate per-scenario based on their context.
- Not exhaustive. Twelve scenarios are the *baseline*. Real implementation will discover additional scenarios as edge cases surface. New scenarios get added to the acceptance test suite and the suite is re-run from scenario 1 forward to verify no regression.
- Not a substitute for the architecture. Sections 1-7 define what gets built. Section 10 defines how the build proceeds. Both are required reading before code starts.

## 11. Changelog

### v0.1 → v0.2

Five components decomposed to four. "Synthetic user" split into seeder and steering brain. "Spine controller" split into steering brain and evaluator. One steering brain with multiple trigger surfaces. Action-pattern triggers introduced. Universal pre-prompt trigger `[steering-director:]`. Critical review added to warm-start seeder.

### v0.2 → v0.3

TBD-2b resolved: The Prompt + web search as v1 brain reasoning engine. Layer 6 sovereignty adapted: triple-check replaces human escape. Dispatch lock added to prevent recursive triple-checks. FM-9 and FM-10 documented.

### v0.3 → v0.4

TBD-1 resolved as out of scope. Triage gate added as auxiliary layer. Preprocessor option considered and rejected.

### v0.4 → v0.5

Stop-decision logic added to seeder as prompt-level instruction. Refinement-of-refinement threshold landed. Four stop reason codes defined. TBD-10 collapsed into TBD-1b. FM-11 and FM-12 added.

### v0.5 → v0.6

Major reframing: Claude Code is the agentic loop, not us. Section 1.5 (inheritance inventory) added. Steering brain sharpened: framework's reasoning as default, Prompt as escalation only.

### v0.6 → v0.7

TBD-6 and TBD-7 closed — neither is an architecture question. Architecture made framework-agnostic. TBD-5 given v1 reference answer.

### v0.7 → v0.8

Seeder restructured around multi-lens reflection. Six lenses, seeder selects relevant per cycle. Stop decision emerges from skeptical lens winning. The "warm start" framing retired. Implementation likely uses The Prompt. FM-13 added. Document cleanup: header bloat reduced, historical references stripped, design principles consolidated.

### v0.8 → v0.9

**Context steward added as fifth built component (section 2.7).** Continuous monitoring during cycle execution; suggests compact/clear/delegate/interrupt when context quality at risk. Distinct from all other components because it operates continuously rather than event-driven or at boundaries. Tested against Principle 1's bar for adding components: different operational model, different reasoning surface, different cost profile, non-foldable. Passes on all four.

**Seeder extended with cycle preparation (section 2.1).** Beyond multi-lens reflection and goal generation, the seeder now also prepares each cycle for context-efficient execution: specificity check on the goal, tool/MCP configuration recommendation, subagent opportunity identification. Same reflection pass; expanded output. Cycle wrapper applies preparation before framework session starts.

**Evaluator extended (section 2.5).** Now also audits steward interventions and seeder preparation effectiveness in addition to its existing audits.

**Three new failure modes** named: FM-14 (silent context degradation, prevented by steward), FM-15 (steward over-intervention), FM-16 (over-preparation drift).

**Principle 6 added.** Build quality into the process, don't inspect it in afterward (Deming). Explicitly acknowledged as the design lineage this architecture draws on; runs through several of the existing principles but worth naming directly.

**TBD-11 added.** Context steward design specifics — monitoring mechanism, intervention thresholds, override rules, cost optimization.

**Component count.** Built: 5 (seeder, brain, steward, evaluator, triage) plus the cycle wrapper. Auxiliary: 1 (triage). Inherited: executor (framework) + external world. Configured: memory, observation, model selection.

The v0.9 update was driven by external course material (Anthropic Claude Code 101: Context Management module) bringing the context-management dimension into focus. The architecture had treated context as the framework's internal concern; v0.9 recognizes that the human role around context (running `/context`, deciding when to `/compact` or `/clear`, identifying subagent opportunities) is a real human-substitute role that needs its own component. Steward handles it continuously; seeder's cycle preparation handles the pre-cycle dimension.

### v0.9 → v1.0

**Vocabulary section added (section 0).** Explicit mapping between Synthetic User wrapper terms and Claude Code native terms. "Cycle" (wrapper view) and "Turn" (CC view) refer to the same boundary; "Run" names the multi-cycle goal-pursuit unit that has no CC equivalent. Confirmed by reading CC's own source code documentation (DeepWiki) and CC blog material — our "cycle" cleanly maps to CC's "turn".

**Hybrid synth-user dispatch resolved (sections 2.2, 2.4).** v0.9 left open whether the synth-user dispatch should be proactive (pre-prompt instruction) or reactive (skill-triggered on halt). v1.0 ships both, hybrid by default. Proactive entry via `SessionStart` hook; reactive entry via `Stop` hook with a router sub-mechanism that classifies turn-end responses as completion-vs-halt. Failure modes of the two paths are uncorrelated, so the hybrid covers both.

**Stop-hook router added as sub-mechanism of brain dispatch (section 2.4).** Three-stage classification cascade (rules → Haiku → default-to-completion) decides whether a `Stop`-hooked turn routes to brain or evaluator. Same pattern as the triage gate from TBD-9. Dispatch lock extended to span both proactive and reactive entry points (FM-10 update).

**Steward / autocompact coordination resolved (section 2.7).** Steward acts at ~60% of our counted tokens; CC's autocompact fires around ~80% of its own count. We undercount (no visibility into CC's hidden system prompt, tool schemas, framework scratchpad), so 60%-of-ours sits around 70-75%-of-CC's — comfortably before autocompact. The threshold gap absorbs estimation drift. Steward's other interventions (delegate, interrupt) remain orthogonal to autocompact.

### v1.0 → v1.1

**Decision Reports added as cross-cutting subsystem (section 2.8).** Every component documents its reasoning in a structured, schema-validated report. Reports route through the evaluator (preserves v0.9 write-gating); evaluator self-reports are the single exception. Two-tier reporting accommodates the steward's continuous-monitor cost profile.

**Section 2.6 write-gating exception documented.** Decision Reports buffer through the evaluator; the evaluator self-reports directly. These are the only modifications to v0.9's "only the evaluator writes" rule.

**Section 2.5 evaluator extended.** Gains schema-validator role (6th sub-function) plus self-reporting mandate. Evaluator is now the system's audit trail enforcer.

**FM-17 added: Decision Report inflation / audit noise.** Continuous-monitor components risk drowning genuine decisions in routine noise. Mitigated by two-tier reporting and 30-day summarization of routine pings.

**TBD-8 split** into TBD-8a (observation surface, consumer side, unchanged) and TBD-8b (Decision Report schema specifics, producer side, partially resolved at v1.1).

**Section 9 component summary updated.** Decision Reports added as a third infrastructure subsystem alongside External World and Memory.

**Cost note.** Decision Reports add ~10,500 tokens of audit material per typical 2-cycle Run. Storage policy and retention defaults are documented in section 2.8.

### v1.1 → v1.2 (LOCKED — FINAL ARCHITECTURE)

**Architecture phase closes here.** Twelve revisions, three named co-designers (Tue as integration layer + design critic; ChatGPT and Gemini as v0.1 contributors; Claude as drafting partner throughout). All TBDs resolved. Section 8 retained as historical record of decisions, not active TBD list.

**Section 10 added: Implementation Strategy.** Acceptance-test-driven build, three test layers (acceptance primary, contracts defense-in-depth on interfaces, targeted unit tests on deterministic gnarly logic), twelve baseline acceptance scenarios locked, build order recommended (1 → 2 → 3 → 4 → 6 → 9 → 10 → 5 → 7 → 8 → 11 → 12). Explicit anti-pattern rejection: mocking LLM-calling components defeats the purpose of testing this kind of system.

**Principle 6 extended.** "Build quality into the process" gains an operational corollary: acceptance tests are upstream of code, not downstream. This is the testing equivalent of designing quality in. The full implementation strategy in section 10 is the operationalization of this principle.

**Section 8 restructured.** Renamed from "Open design decisions" to "Design decision history (all resolved at v1.2)." Every TBD marked resolved with locked-at version. Summary statement: zero architecture work remaining.

**Status line changed.** From "Design refined through N revisions, implementation pending" to "ARCHITECTURE LOCKED — design phase complete, implementation begins from this document."

**What comes next is code.** This document is now reference, not draft. Edits beyond v1.2 happen only if implementation discovers an architectural assumption that doesn't hold — in which case the doc gets a v1.3 with a clear "discovered during implementation" entry. Refinements to the implementation strategy (more scenarios, better build orders) happen in section 10 without bumping major versions.

**TBD-11 partially resolved (section 8).** Token estimation method and autocompact coordination locked. Monitoring mechanism and non-compact intervention thresholds remain v1 build work.

**No new failure modes.** The two FM additions considered (Stop-hook misclassification, threshold-gap-too-narrow) folded into FM-10 update and section 2.4/2.7 prose. The architecture stands at 17 failure modes (FM-1 through FM-17).

### v1.2 → v1.3 (IMPLEMENTATION-READY — pre-build audit fixes)

A pre-implementation audit (2026-06-08) re-read the locked v1.2 architecture against Claude Code's real extension surface, verified repo/sandbox/GitHub sync (all clean), and found eight holes. v1.3 resolves all eight. The status moves from "LOCKED (design complete)" to "IMPLEMENTATION-READY."

**The consequential one: proactive dispatch re-grounded on an MCP tool (sections 2.2, 2.4, 2.9).** v1.0–v1.2 had CC emit a `[steering-director:]` magic string mid-turn for a hook to catch and answer. No CC hook fires on arbitrary mid-turn text, so that path was not buildable. v1.3 replaces it with a synchronous `consult_director` MCP tool: CC calls it instead of asking the user, blocks for the result, and continues in-turn. The reactive `Stop`-hook path is now standardized on native block-and-continue (not the previously-described "synthesize a follow-up `UserPromptSubmit`").

**New section 2.9 (Integration surface).** Specifies the orchestrator process, the exact hook→mechanism mapping (`consult_director` MCP tool, `Stop`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionStart`), cross-invocation state, the single-writer concurrency model, and the two pinned external dependencies (vendored The Prompt; pluggable search backend for restricted environments).

**Context steward mechanism corrected (section 2.7).** From "continuous mid-thought monitoring" to honest per-tool-call (`PostToolUse`) cadence; the four interventions mapped to real CC mechanisms; `suggest_interrupt` acknowledged as best-effort at the next tool boundary.

**Evaluation-criteria source pinned (sections 2.1, 2.5).** Cycle 0 criteria from CC's wrapper-prompted done-when declaration; cycle N>0 from seeder preparation. Evaluator sub-function count corrected (six → seven).

**Run↔session mapping pinned (section 0):** one Run = one CC session for v1.

**Two new failure modes:** FM-18 (dispatch escape) and FM-19 (hook handler failure), each with fail-safe mitigations. Architecture now at **19** failure modes. The v1.2 changelog's "stays at 16" was itself a miscount (it was 17 after FM-17); corrected here.

**Two new acceptance scenarios:** 13 (dispatch escape caught post-hoc) and 14 (hook handler fails safe). Baseline is now 14 scenarios; build order updated to 1 → 2 → 3 → 4 → 6 → 9 → 10 → 5 → 7 → 8 → 13 → 14 → 11 → 12.

**Cosmetic fixes:** stale "this is v0.9 / six TBDs open" lines in sections 7 and 9 corrected to v1.3; a garbled sentence in section 2.4 repaired; TBD provenance lines made accurate.

**What comes next is still code** — now genuinely so. The mechanism questions that would have blocked the walking skeleton (proactive dispatch, criteria source, Run↔session, The Prompt) are answered. Scenario 1 can be built.