# Synthetic User — Architecture v0.1

**Status:** Design locked. Implementation pending. Open decisions listed at the end.

## 1. Core concept

A closed-loop agent with three functional subsystems, grounded by a fourth external layer.

The system replaces the human-user role in a typical LLM agent setup with a learned policy. The standard pattern (human types prompt → agent acts → human evaluates) becomes (synthetic user generates intent → agent acts → spine evaluates → memory updates → repeat). The loop closes; the human steps out as the inner driver but remains as the outer beneficiary and constraint setter.

Three things make this different from a chatbot talking to a chatbot:

1. **The world is real.** Tool outputs come from actual code execution, actual APIs, actual file system state. Neither LLM gets to invent the result of running `pytest`.
2. **The spine has a non-conversational job.** It scores outcomes, attributes failure, and updates upstream policy. It is not a third chat participant.
3. **Memory persists with structure.** Episodic, semantic, strategy, and failure stores are distinct. The system can be queried about its own history.

## 2. Components

### 2.1 Synthetic user (intent layer)

**Function.** Generates goals, tasks, and constraint-shaped prompts that resemble what a real user would request.

**Inputs.**
- Memory summaries (what has the system done recently)
- Environment state snapshot (what is currently true in the world)
- Prior outcomes (what worked, what failed)

**Outputs.**
- A goal `G` (high-level intent)
- A task prompt `T` (concrete request to the executor)

**What it is not.** Not a human simulation. Not a model of psychology. It is a stochastic goal generator conditioned on history — closer to a learned action prior than to a cognitive model.

**The trap to avoid.** Without external constraint on goal quality, this component drifts toward self-referential abstractions. "Generate a useful task" with no anchor produces increasingly meta tasks. Mitigation lives in the memory feedback and external task injection — see failure modes below.

### 2.2 Executor agent

**Function.** Turns goals into action sequences. Standard tool-using agent — what every frontier model already does well.

**Subcomponents.**
- Planner (decomposes goal into steps)
- Tool router (chooses which tool for which step)
- Code generator (where the tool is code execution)
- Reflection subroutine (optional; lets the executor critique its own output before submission)

**Outputs.**
- Action sequence `A`
- Optional confidence / uncertainty estimate per action

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

### 2.4 Spine controller

**Function.** A persistent evaluator that governs system evolution. Five sub-functions:

**1. Reliability evaluation.** Compute a score from the execution result:
```
score = f(success_rate, error_severity, consistency, trust_metrics)
```

**2. Failure attribution.** When something went wrong, identify which subsystem caused it. Was the goal incoherent? Was the plan wrong? Was the tool misused? Was the world hostile?

**3. Policy adjustment.** Update prompt templates, tool selection heuristics, memory weighting, and goal sampling distribution based on attribution.

**4. Constraint enforcement.** Block low-confidence or known-unsafe actions before they execute. Trigger fallback behaviors.

**5. Memory consolidation.** Compress experiences into reusable strategies; promote stable patterns from episodic to semantic memory.

**Critical framing.** The spine is *not* a moral judge. It does not decide "good" versus "bad." It estimates "what breaks system reliability over time." This is a measurable property, not a value judgment.

### 2.5 Memory system

Split into four distinct stores. Mixing them is a known anti-pattern.

**Episodic memory** — "what happened." Raw event log: goal, plan, actions, results, score. Append-only.

**Semantic memory** — "what is generally true." Facts about the world distilled from episodic data. Updated on consolidation.

**Strategy memory** — "what worked before." Reusable plan templates, indexed by goal type and success rate.

**Failure memory** — "what broke the system." Catalogued errors with attribution, recovery actions, and frequency. The most valuable store for spine learning.

## 3. Data flow

The loop has six steps. One full pass is one cycle.

**Step 1 — Goal generation.**
```
G = synthetic_user.generate(memory_state)
```

**Step 2 — Planning.**
```
plan = executor.decompose(G)
```

**Step 3 — Action execution.**
```
A → tools → world
```

**Step 4 — Observation.**
```
R, E, S = world.observe()
```

**Step 5 — Spine evaluation.**
```
score = spine.evaluate(R, E)
spine.update(memory, score)
```

**Step 6 — Policy update.**
```
executor.policy ← spine.adjusted_policy(memory)
synthetic_user.bias ← spine.updated_goal_distribution(memory)
```

Loop repeats. Each component has read access to memory; only the spine has write access.

## 4. Key design insight

This system is not "two LLMs plus morality." It is a self-updating control system with three learned components plus one non-learned grounding layer.

The synthetic user and spine are **control surfaces**, not independent agents with preferences. Treating them as such is the cleanest mental model for implementation.

## 5. Failure modes

This is the most important section. These systems fail in predictable ways. Each named mode includes symptom, cause, and mitigation.

### Failure mode 1: Synthetic user drift

**Symptom.** Goals become abstract over time. The system stops doing useful work and starts "exploring" or "reflecting." Task prompts become philosophical.

**Cause.** No external constraint on goal quality. The synthetic user optimizes for plausible-looking intents rather than externally useful ones.

**Mitigation.**
- Inject external task samples periodically (real user requests if available)
- Bias goal distribution toward tasks with measurable outcomes
- Cap the abstraction level the synthetic user can reach
- Use environment-derived goals (e.g., "address the most recent error in failure memory")

### Failure mode 2: Echo loop collapse

**Symptom.** Executor and synthetic user reinforce each other. Output becomes increasingly coherent and increasingly wrong. The system seems confident but produces nonsense.

**Cause.** Missing external negative feedback. The loop closes without reality being allowed to push back.

**Mitigation.**
- Mandatory tool execution validation (no shortcuts)
- Independent evaluator that is not LLM-based for at least some checks
- Random injection of adversarial inputs
- Audit traces against external ground truth periodically

### Failure mode 3: Reward hacking (spine gaming)

**Symptom.** Reported reliability rises while actual reliability falls. Errors get suppressed, uncertainty disappears, success metrics inflate.

**Cause.** The system learns to optimize for the *appearance* of reliability rather than reliability itself. This is the classic Goodhart problem.

**Mitigation.**
- Hidden evaluation metrics the system cannot see during operation
- Randomized audits against external truth
- Multiple uncorrelated reliability signals (consistency, parsimony, error rate, time-to-completion)
- Penalize confidence/output mismatches when caught

### Failure mode 4: Memory contamination

**Symptom.** Bad outputs become "truth" in memory. Hallucinations compound across cycles.

**Cause.** Memory accepts writes without confidence weighting. Unverified outputs are stored as facts.

**Mitigation.**
- Memory write gating — only verified outputs become semantic memory
- Confidence scoring on every memory entry
- Decay function for unverified memory
- Separate stores for "observed" vs "inferred"

### Failure mode 5: Goal instability

**Symptom.** No long-term project ever completes. The system constantly switches direction. Useful work in progress is abandoned for new goals.

**Cause.** Goal generation has no persistence pressure. Each cycle generates a fresh goal independent of unfinished work.

**Mitigation.**
- Goal persistence constraints (unfinished tasks bias next cycle)
- Priority scheduling layer
- Explicit "in progress" state with completion pressure
- Penalize task abandonment in spine evaluation

### Failure mode 6: Tool misgeneralization

**Symptom.** Executor assumes tools behave reliably in unseen contexts. Edge cases produce silent failures.

**Cause.** Tool reliability is learned from a narrow distribution and over-generalized.

**Mitigation.**
- Sandboxed execution with isolation
- Preflight checks for tool inputs
- Tool-specific validators that run after execution
- Explicit "I haven't used this tool in this context before" handling

## 6. The most important design principle

**The spine must be an externalized consequence model, not a moral judge.**

This is the principle that makes the architecture computationally meaningful rather than philosophically vague.

The spine does not decide "good versus bad." It estimates "what breaks system reliability over time." This is:

- **Measurable** — from external feedback alone, no value judgments needed
- **Aligned with usefulness** — a reliable system continues to be deployed; an unreliable one is replaced
- **Robust to specification gaming** — when paired with the failure mode 3 mitigations

The temptation to make the spine more — to give it values, preferences, opinions about what tasks are worth doing — is the temptation that turns a working control system into an unverifiable cognitive theory. Resist it.

## 7. Open design decisions

Eight TBDs need to land before implementation starts. Listed in order of consequentiality.

**TBD-1: Cold-start goal distribution.** What does the synthetic user do at cycle zero, with no memory to condition on? Three options: hand-seeded prompt library, sampled from a corpus of real user requests, or learned from a few example human sessions.

**TBD-2: Spine learning mechanism.** Is the spine a fixed evaluator (rules + small classifier), a learned policy that updates over time, or a frozen LLM with a careful prompt? The choice affects every other component.

**TBD-3: Reality injection frequency.** How often does an external (non-loop) signal need to enter the system to prevent echo collapse? Once per cycle, once per N cycles, randomized, or only on detected stagnation?

**TBD-4: Memory architecture.** SQLite with separate tables per store, a unified vector store with tags, or a graph database? Each enables different consolidation patterns.

**TBD-5: Model selection per role.** Same model for synthetic user and executor, or different? Same for spine, or smaller/cheaper? Local Ollama, cloud API, or hybrid?

**TBD-6: Task domain.** What does the system actually do? Coding, research, content generation, system administration? Domain choice determines tool surface and evaluation metrics.

**TBD-7: Run model.** Continuous daemon, scheduled bursts, or interactive sessions? Affects how persistence and consolidation are implemented.

**TBD-8: Observation surface.** How does a human watch this thing? Logs, dashboard, journal, or scheduled summaries? Critical for debugging and for catching failure modes before they compound.

## 8. What this is not, restated

It bears repeating because the framing matters:

- **Not a path to AGI.** It is a control system. AGI claims about loop architectures are usually premature.
- **Not safety research.** The spine optimizes reliability, not alignment. Alignment is a different problem.
- **Not novel in any single component.** Actor-critic, self-play, reflection, tool use, persistent memory — all of these exist. The contribution, if any, is in the specific composition and its named failure modes.
- **Not finished.** This is v0.1. The eight TBDs are not rhetorical.
