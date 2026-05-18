# Synthetic User — Architecture v0.9

**Status:** Design refined through multi-turn collaborative critique across nine revisions. Implementation pending. Open decisions listed in section 8.

**What this is.** A closed-loop agent architecture that wraps an existing agentic framework (Claude Code as v1 reference) with infrastructure that replaces the human roles ordinarily sitting around such a loop. The framework does the cognitive work inside cycles; this project builds the substitutes for the human who would otherwise drive the framework from outside.

**Project naming note.** "Synthetic User" is the project name. Inside the project, the components have specific names: **triage gate** (request screening), **seeder** (cycle-boundary reflection, goal generation, and cycle preparation), **steering brain** (in-flight resolution), **context steward** (continuous context monitoring), **evaluator** (post-hoc learning). The project replaces the human user; the components handle specific slices of that replacement.

**For version history, see section 10 (changelog).**

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
- **Steering brain dispatch.** The intercept that catches the framework's `[steering-director:]` emissions, holds the triple-check lock, invokes The Prompt when escalation is needed, returns verdicts. The framework handles most situations on its own; the brain dispatch only fires when the framework itself would have asked.
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

**Pre-prompt instruction.** Every framework session begins with the universal trigger instruction: *when you would have asked the user a question to proceed, instead emit `[steering-director: <your question>]` and continue based on the response you receive.* This is the one-sentence rule that converts every framework doubt into a steering brain invocation.

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

**Trigger surfaces.** The brain is invoked from two kinds of triggers:

**Trigger Type 1: Framework doubt.** The framework was about to ask the user a question. Per the universal pre-prompt instruction, it emits `[steering-director: <question>]` instead. The brain receives the question.

**Trigger Type 2: Action pattern match.** A registered action-pattern skill detects the framework is about to perform an action of interest. The skill routes to the brain. The brain receives the about-to-happen action.

These are the same brain. The triggers are heterogeneous; the judgment is unified.

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

**The brain dispatch wrapper.** Small layer that handles trigger payload normalization, verdict normalization, escalation detection, and triple-check state tracking for Layer 6.

**Layer 6 sovereignty: triple-check, not human escape.**

When Layer 6 fires from a top-level escalation:

1. **Pass 1:** The Prompt runs on the question. Produces an answer.
2. **Pass 2 (critique):** The Prompt runs again, with Pass 1's answer as input. Web search invoked.
3. **Pass 3 (reconciliation):** The Prompt runs a third time, with Pass 1 and Pass 2 as input.

The Pass 3 verdict is returned to the framework. The cycle continues normally. Reality validates post-hoc via the evaluator.

**Recursion protection: the dispatch lock.** A binary `in_triple_check` flag held by the dispatch wrapper prevents nested triple-checks. While held, Layer 6 fires from inside Pass 1/2/3 contribute content but do not bootstrap new triple-checks.

**Recording for the evaluator.** Each triple-check fire is flagged in episodic memory.

**Authority.**
- Can halt the framework (on irreversible operations or hard constraint violations)
- Can redirect attention to existing context
- Cannot escalate to the human — structurally forbidden
- Cannot inject new context

**Critical framing.** The brain is operational, not ethical. It decides what should happen, not what is good.

**Replaces what human did.** The human watching the screen and the human answering the framework's questions.

### 2.5 Evaluator (post-hoc learner)

**Function.** Runs once per cycle, after the cycle completes. Six sub-functions:

1. **Reliability evaluation.** Scores the cycle against declared criteria.
2. **Failure attribution.** When something went wrong, identifies which subsystem caused it.
3. **Trigger set adjustment.** Updates the action-pattern skill set.
4. **Brain prior adjustment.** Updates the steering brain's resolution priors.
5. **Steward intervention audit.** Reviews context steward decisions during the cycle. Did the compact help or hurt? Did the suggested subagent delegation save context without losing fidelity? Tunes the steward's intervention thresholds over time.
6. **Memory consolidation.** Compresses episodic events into reusable strategies.

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

### 2.7 Context steward (continuous monitor)

**Function.** Continuously tracks framework context state during cycle execution. Intervenes when context quality is at risk. Runs in parallel with the framework throughout each cycle; goes quiet when context is healthy.

**Operational model.** Distinct from all other components. The triage gate fires once per request. The seeder fires at cycle boundaries. The steering brain fires on triggers (framework doubt or action pattern). The evaluator fires once per cycle close. **The context steward runs continuously** during cycle execution, polling or hooking into framework state to monitor context utilization, recent additions, and content patterns.

This continuous operation is what makes the steward its own component rather than a folded responsibility. Context can fill or degrade at any moment — mid-thought, mid-tool-call, mid-reasoning — and the natural response moments for the other components (boundaries, triggers, post-hoc) all miss the in-the-moment quality of context state.

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

**Implementation note.** Could be a thin LLM-based monitor (small model, narrow prompt, runs periodically), or partially rule-based (utilization thresholds trigger rule-based checks, LLM only for ambiguous cases). v1 hybrid is likely best — rules for clear thresholds (>80% utilization → suggest compact), LLM for nuance (is this exploration polluting main context, or is it core to the goal?).

**Cost note.** The only component that runs continuously. Cost matters more here than for other components. Should be the smallest viable model (Haiku-tier in v1 reference). Invoked periodically (every N framework steps, or every M seconds, or hook-based on context state changes) rather than per-token.

**Recording for the evaluator.** Every steward intervention is logged in episodic memory: what triggered it, what action was suggested, whether the framework followed it, what the downstream effect was. The evaluator uses this to tune intervention thresholds and identify steward errors (FM-15).

**Replaces what human did.** The human running `/context` to check state, deciding when to `/compact`, deciding when to `/clear`, deciding when to spawn subagents for context-saving purposes. The course's whole "context management" topic is what this component does.

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
   - 4b. If the framework would have asked the user a question, it emits `[steering-director:]`.
     - **Steering brain fires (trigger type 1)** → verdict → framework reads as reply
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

**Principle 6 (new in v0.9): Build quality into the process, don't inspect it in afterward.**

(Deming.) The architecture's design choices reflect this consistently. The seeder's cycle preparation (specificity, tool config, subagent identification) builds context efficiency into the cycle's start rather than letting context problems emerge for the steward to fix mid-cycle. The triage gate builds work-fitness into the entry rather than letting the engine process unfit work. The action-pattern triggers build irreversibility caution into action moments rather than catching mistakes afterward. The principle that ties these together: when quality can be designed into a phase, prefer that over hoping later phases will correct for upstream variance.

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

**Mitigation.** The dispatch layer's binary `in_triple_check` lock prevents nested triple-checks.

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

## 7. What this is, restated

It bears repeating because the framing matters:

- **Not a path to AGI.** It is a control system around an existing agentic framework.
- **Not safety research.** The components optimize reliability, not alignment.
- **Not novel in any single component.** Actor-critic, self-play, reflection, tool use, persistent memory, multi-perspective evaluation, context management — all of these exist. The contribution, if any, is in the specific composition: the decomposition of "the human in the loop" into roles, the substitution of named components for the roles that need building, the inheritance of the rest from the framework.
- **Not human-in-the-loop.** A standard agentic-workflow framing positions the human as a governor reviewing the agent's plan before execution. The synthetic-user architecture deliberately rejects this. The triage gate is the only place a human can be involved, and it sits *before* the loop runs, not as a checkpoint inside it. Once the gate accepts the request, the system runs to completion without human approval at any intermediate step. Safeguards are structural (multi-lens reflection, context monitoring, external grounding, post-hoc evaluator learning) rather than procedural.
- **Not finished.** This is v0.9. Six TBDs remain open.

## 8. Open design decisions

### Genuine architecture / design work (ours to land)

**TBD-1b (resolved in v0.8, extended in v0.9): Seeder cycle-boundary reflection structure.** Multi-lens reflection with six potential lenses. Stop decision emerges from skeptical lens winning the synthesis. v0.9 extends with cycle preparation as part of seeder output (specificity, tool config, subagent opportunities). Implementation details (specific lens prompts, selection rules, synthesis format, preparation format) are v1 build work.

**TBD-2a: Evaluator learning mechanism.** Fixed evaluator (rules + small classifier), learned policy that updates over time, or frozen LLM with a careful prompt? The evaluator is the largest single piece of new build work.

**TBD-9: Triage gate design.** Classifier mechanism, the set of simple-handle paths shipped in v1, the log format for evaluator audit, and the threshold for rejection.

**TBD-11 (new in v0.9): Context steward design.** Monitoring mechanism (polling, hook-based, or hybrid), suggestion threshold tuning, intervention authority and override rules, cost-optimization. The steward's continuous operation means cost matters more here than for other components.

### Configuration / specification (light architecture work)

**TBD-2c: Initial action-pattern trigger set.** Most action-pattern detection is inherited from the framework's own pause instincts. The custom layer is small.

**TBD-4: Memory architecture.** SQLite tables / memory MCP / vector store / graph DB.

**TBD-5: Model selection per role.** v1 reference: Claude tiers across roles (Haiku for triage and steward, Sonnet for seeder and brain, Opus for evaluator and Layer 6).

**TBD-8: Observation surface.** Logs / dashboard / journal / scheduled summaries.

### Resolved or closed

- **TBD-1** — Cold-start goal source: out of scope (v0.4)
- **TBD-1b** — Cycle-boundary reflection: multi-lens model + cycle preparation (v0.8, extended v0.9)
- **TBD-2b** — Steering brain implementation: framework's reasoning as default + The Prompt as Layer 6 escalation (v0.3, sharpened in v0.6)
- **TBD-3** — Reality injection frequency: dissolved (v0.2)
- **TBD-6** — Task domain: closed; domain-agnostic (v0.7)
- **TBD-7** — Run model: closed; run-model-agnostic (v0.7)
- **TBD-10** — Completion gate: collapsed into TBD-1b (v0.5)

### Summary of remaining work

Three genuine design questions: **TBD-2a (evaluator), TBD-9 (triage gate), TBD-11 (context steward).**

Four configuration items: **TBD-2c, TBD-4, TBD-5, TBD-8.**

Seven TBDs total. The architecture is locked enough to begin v1 implementation against.

## 9. Component summary

For quick reference, the system at v0.9 consists of:

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

Five components we build (seeder, brain dispatch, context steward, evaluator, plus triage gate as auxiliary), plus the cycle wrapper that orchestrates them. The executor is the framework. The world is what the framework's tools touch. Memory is configured, not built.

## 10. Changelog

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