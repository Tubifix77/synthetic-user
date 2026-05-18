# Synthetic User — Research Findings

**Date:** 2026-05-18
**Status:** Research complete for TBD-4 (memory), TBD-2a (evaluator), TBD-9 (triage gate). Recommendations ready for architecture incorporation.
**Sources:** Web research across academic surveys (arXiv 2603.07670), production framework comparisons (Vectorize, SurePrompts, Zylos), and engineering pattern guides (Principia Agentica, Mavik Labs, AWS).

This document presents research-backed recommendations for the three remaining design TBDs in the synthetic-user architecture (v0.9). Each section states the question, summarizes the production landscape, presents the recommendation, and notes alternatives.

---

## TBD-4: Memory Architecture

**The question.** For a four-store system (episodic, semantic, strategy, failure) with cross-store consolidation, evaluator-only writes, and multiple readers — what storage backend should v1 use?

### Landscape (2026)

Five distinct architectural camps dominate production agent memory:

1. **Provider-managed** (ChatGPT memory, Claude Projects). Zero engineering effort, zero control. Wrong for synthetic-user — we need to query, audit, and own the schema.

2. **Self-managing agent** (Letta/MemGPT-style). The agent edits its own memory blocks via tool calls. Memory hygiene happens inside the agent loop. Heavy: adds token cost on every turn for memory reasoning. Wrong fit because synthetic-user's executor is the framework (Claude Code), not a Letta-style agent.

3. **Memory layer** (Mem0-style). Drop-in CRUD API with multi-level scoping. Vector + optional knowledge graph. Low friction, ~week to ship. Strong personalization, weaker on cross-cycle learning patterns.

4. **Vector-only RAG-as-memory**. Cheap, simple, read-only. Cannot update or contradict stored facts. Wrong for synthetic-user — the evaluator needs to update brain priors, trigger weights, and consolidate strategies, all of which are writes.

5. **Custom in-app schema** (Postgres/Redis tables + summarizer). Maximum control, maximum maintenance. Usually the right end state, not the right starting point.

### The decision framework (from SurePrompts 2026)

Three questions:

1. **Do you control the model and orchestration loop?** Yes (we own the wrapper).
2. **Is memory load-bearing or incidental?** Load-bearing — the evaluator needs persistent cross-cycle learning. The synthetic-user hypothesis depends on memory being load-bearing.
3. **Do you need user-scoped persistence?** Yes, scoped per session and per deployment.

Per the framework: load-bearing memory points to Letta or custom. Letta is wrong fit (the executor isn't a Letta agent). That leaves custom schema.

### The four stores mapped to storage

The synthetic-user architecture has four stores with different access patterns:

| Store | Access pattern | Right backend |
|---|---|---|
| **Episodic** | Append-only event log, time-ordered queries, chain-of-events retrieval | SQLite table (timestamp index) |
| **Semantic** | Conceptual queries, similarity search across distilled facts | Vector store (embeddings) |
| **Strategy** | Lookup by goal type, ranked by success rate | SQLite table (goal_type index) + optional vector for similar-goal retrieval |
| **Failure** | Lookup by error category, frequency, attribution chain | SQLite table (category + attribution_chain indexes) |

Three of four stores are structured row-oriented data. Only semantic memory genuinely needs vector search. This is not a unified vector store problem.

### Recommendation for v1

**SQLite for three stores + pgvector or local FAISS for semantic memory.**

Concretely:

- Single SQLite database (`synthetic_user.db`) with three tables: `episodic`, `strategy`, `failure`
- A vector store for semantic memory. Two viable options:
  - **pgvector** if the deployer already runs Postgres (Skynet does not; synthetic-user is greenfield)
  - **FAISS** locally with simple Python wrapper (no separate service, embedded with the daemon)
  - **Chroma** as third option if a separate process is acceptable

**Why this maps cleanly to the architecture:**

- The evaluator's write-gating is enforced trivially (only the evaluator process has write access to the DB)
- Episodic memory's append-only requirement is one SQLite transaction pattern
- Cross-store consolidation runs as a periodic job (evaluator at cycle close) reading from episodic, writing distilled facts to semantic, promoting stable patterns to strategy, recording attributed errors in failure
- The four-store separation matches Skynet's proven pattern (episodic with HMAC chain, semantic via beyondRAG, failure memory, learned rules)

### What we are NOT using

- **Mem0** — wrong abstraction. Mem0 wraps user-conversation memory for chat agents; our memory is system-state memory across cycles, not per-user conversation memory.
- **Letta** — wrong abstraction. Letta is for agents that edit their own memory mid-loop; our executor is the framework (Claude Code), which does not edit synthetic-user memory.
- **Knowledge graph (Neo4j/Graphiti)** — overkill for v1. Three of four stores don't need graph traversal. If cross-cycle entity relationships become important in v2, this can be added.
- **Mem0-style hybrid vector+graph** — premature.

### Implementation outline

```
data/
  synthetic_user.db          # SQLite — episodic, strategy, failure tables
  semantic/
    chroma.db                # or faiss.index — semantic memory vectors
```

Schema sketch:

```sql
CREATE TABLE episodic (
  id INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL,
  cycle_n INTEGER NOT NULL,
  ts INTEGER NOT NULL,                  -- unix epoch ms
  kind TEXT NOT NULL,                   -- 'goal'|'action'|'brain_verdict'|'steward_intervention'|...
  payload JSON NOT NULL,
  attribution JSON                      -- nullable; set on failure events
);
CREATE INDEX idx_episodic_session_ts ON episodic(session_id, ts);

CREATE TABLE strategy (
  id INTEGER PRIMARY KEY,
  goal_type TEXT NOT NULL,
  template JSON NOT NULL,
  success_rate REAL,
  use_count INTEGER DEFAULT 0,
  last_used INTEGER
); -- index on goal_type

CREATE TABLE failure (
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL,               -- FM-1..FM-16
  attribution_chain JSON,
  recovery_action TEXT,
  frequency INTEGER DEFAULT 1
); -- index on category
```

Semantic memory is a separate concern wrapped by `core/memory/semantic.py` which talks to Chroma or FAISS via a thin interface; the rest of the codebase doesn't see which backend is used.

### Cost note

This stack runs entirely locally with no API calls except the optional embedding model. Storage is bounded by the deployer (rotate episodic events older than N days, decay unverified semantic facts). On Tue's hardware (16 GB RAM, no high-volume agent traffic), this fits comfortably in memory.

---

## TBD-2a: Evaluator Learning Mechanism

**The question.** Is the evaluator a fixed evaluator (rules + small classifier), a learned policy that updates over time, or a frozen LLM with a careful prompt?

### Landscape (2026)

The Zylos 'LLM-as-Judge in Production' survey (April 2026) found six distinct patterns:

1. **Offline evaluation harnesses** (Braintrust, LangSmith, Arize Phoenix). Asynchronous, after-the-fact, for development cycles. Not applicable here — we need in-system learning.

2. **Online runtime verifiers**. LLM judge runs in the request path. Latency-sensitive (76–162ms acceptable for small judges, multi-second GPT-4 not).

3. **Self-consistency / self-critique loops**. Multiple generations, vote or rank. Strong in formal domains, weak in open-ended generation.

4. **Reflexion / reflection patterns**. Verbal self-critique stored in episodic memory, reused in subsequent trials. 91% pass@1 on HumanEval (vs GPT-4's 80% baseline). Directly relevant: this is what the evaluator's policy update is.

5. **Constitutional AI / RLAIF**. Training-time pattern. Out of scope for v1.

6. **Reward models in inference-time search**. ORMs and PRMs for tree search. Heavy; not for v1.

### Specifically for failure attribution

The 2025 paper 'Which Agent Causes Task Failures and When?' (ICML spotlight) and the AgenTracer follow-up showed that an 8B model trained specifically for failure attribution outperforms larger proprietary models. This validates the small-specialized-judge pattern.

Open-source judge models worth knowing:

| Model | Size | Strength |
|---|---|---|
| **Prometheus 2** | 7B / 8x7B | Custom rubric evaluation, 72-85% human agreement |
| **Patronus Lynx** | 8B / 70B | Hallucination detection; 8B beats GPT-3.5 by 24.5% on HaluBench |
| **Galileo Luna-2** | 3B / 8B | 0.88-0.95 accuracy at 97% cost reduction vs GPT-4 |
| **JudgeLM** | 7B / 13B / 33B | Bias mitigation built in (swap augmentation, reference drop) |

### Known failure modes for LLM judges

All apply to the evaluator and must be mitigated:

- **Positional bias** — judges favor responses by position. Mitigation: double evaluation with order swap.
- **Verbosity bias** — judges prefer longer responses. Mitigation: score conciseness explicitly.
- **Self-preference / same-family bias** — agreement rates inflate 5-7% when judge and actor share training family. Mitigation: cross-family judge for high-stakes (FM-8 in architecture).
- **Judge hallucinations** — fabricated evaluation rationales. Mitigation: constrained JSON schemas, chain-of-thought exposure.
- **Calibration drift** — judge thresholds drift as data distribution shifts. Mitigation: monthly held-out golden dataset re-validation.
- **Intrinsic self-correction is unreliable** — prompting an LLM to 'check your work' without external grounding degrades performance. Mitigation: only self-correct when grounded in external feedback (tool outputs, test results).

### Recommendation for v1

**Hybrid: rules-based scoring + LLM-based attribution + classifier-based learning.**

Three layers, each with appropriate cost profile:

**Layer 1 — Rules-based scoring (always runs, cheap).**

Deterministic checks at cycle close:
- Did the deliverable exist? (binary)
- Did tests pass if tests were declared? (binary)
- Did the cycle hit the framework's auto-compact? (signal for steward audit)
- Did the brain halt occur? (signal for analysis)
- Did the seeder's preparation match the actual execution? (correlation signal)

These are cheap, deterministic, and produce hard signals. They are the floor of the evaluator.

**Layer 2 — LLM-based attribution (on failure or anomaly, expensive).**

When the rules-layer detects a cycle didn't go cleanly, an LLM judge runs failure attribution:

- Read the cycle trajectory (episodic memory)
- Identify the first decisive error
- Attribute it to a subsystem (seeder / framework / brain / steward / triage)
- Output structured JSON with attribution chain and confidence

For v1 use Claude Opus (Tue's tier choice, also matches Layer 6 escalation model). For v2, this layer becomes a candidate for distillation to a small specialized judge (8B Lynx-style) once enough failure traces have accumulated to fine-tune.

**Layer 3 — Classifier-based learning (background, periodic).**

Trigger weights, brain priors, steward thresholds, triage classifier weights — all of these are updated based on accumulated outcomes. The mechanism is not RL or fine-tuning; it's threshold adjustment driven by a small classifier:

- Input: features of the situation (trigger type, cycle context, prior outcome)
- Output: 'this trigger pattern correlates with `proceed` verdicts that ended badly' or similar
- Implementation: scikit-learn logistic regression or gradient-boosted trees on tabular features extracted from episodic memory

This is the Reflexion pattern but persisted across deployments rather than per-session. The architecture is similar to Skynet's RIPPER-based learned-rule quarantine (which uses `(P-N)/(P+N) > 0.5` and `firings >= 5` as the quarantine threshold).

### Why hybrid not pure-LLM

Three reasons:

1. **Cost.** Pure-LLM evaluation per cycle is too expensive. Hybrid restricts LLM use to actually-anomalous cycles (the ones worth analyzing).
2. **Determinism.** Rules-layer is reproducible; LLM-layer is not. Mixing gives auditable signal alongside nuanced attribution.
3. **Defense in depth.** All three layers can disagree. When they do, that's a yellow flag for human review — exactly the signal a system this novel needs in its first deployments.

### Failure modes this addresses from the architecture doc

- FM-3 (reward hacking / evaluator gaming) — hybrid signals are harder to game than any single signal
- FM-8 (seeder–evaluator collusion) — Layer 2 uses cross-family judge to break model agreement
- FM-13 (lens collapse) — Layer 1 records lens contribution as a measurable feature; Layer 3 flags persistent imbalance
- FM-15 (steward over-intervention) — Layer 3 tracks intervention outcomes; thresholds tune automatically

### What we are NOT using

- **Pure rules-based.** Misses everything Layer 2 catches (subtle failure attribution requires reasoning).
- **Pure LLM-based.** Too expensive per cycle, too prone to judge biases (FM-3, FM-8).
- **RL / fine-tuning.** Out of scope for v1. Layer 3's classifier is the lightweight version of this.
- **Distilled specialized judge (Prometheus 2, Lynx).** Worth considering for v2 once enough failure traces exist for fine-tuning.

---

## TBD-9: Triage Gate Design

**The question.** Classifier mechanism (rules / small LLM / hybrid), set of simple-handle paths shipped in v1, log format for evaluator audit, rejection threshold.

### Landscape (2026)

From the Mavik Labs routing survey: routing decisions account for 70-80% of agent operational costs. The triage gate's classifier is the highest-leverage cost decision in the architecture.

Five classification approaches in production:

1. **Hand-coded regex/keyword rules.** Fast (<1ms), zero cost, brittle. Wrong for nuanced inputs.
2. **Tiny classifier model** (TF-IDF + logistic regression). >95% accuracy on simple/complex classification, single-digit ms inference, free after training. Strong baseline.
3. **Small LLM call** (Haiku-class). 100-500ms latency, low cost per call, handles novel phrasing well, more brittle on adversarial inputs.
4. **Embedding-based intent matching.** Compare incoming query to a labeled corpus via cosine similarity. ~10-50ms, scales to many intents, requires labeled corpus.
5. **Hybrid (rules + LLM fallback).** Rules catch clear cases (cheap), LLM handles ambiguous ones (better quality where it matters).

### Recommendation for v1

**Hybrid: rules for clear cases, Haiku-class LLM for ambiguous, The Prompt for genuinely hard.**

Three-stage cascade:

**Stage 1 — Rules-based fast path (resolves ~70% of requests).**

Pattern-match clear cases against hardcoded lists:

- **Simple lookup (direct handle):** queries matching weather/time/date/currency/single-fact-lookup/basic-web-search patterns
- **Clear reject:** empty input, single-word non-task input, malformed (only special chars), known-too-vague templates ('do something', 'help me', 'idk what to do')
- **Clear loop-worthy:** explicit task verbs (build, refactor, implement, debug, analyze, write, generate, create) combined with object nouns

Latency: <1ms. Cost: zero. Catches the common cases.

**Stage 2 — Small LLM classifier (resolves ~28% of requests).**

When rules don't match clearly, invoke Haiku (or the deployer's chosen lightweight model) with a structured prompt:

```
Classify this user request into exactly one route:
- LOOP_WORTHY: multi-step work requiring planning, tool use, or verification
- SIMPLE_LOOKUP: single-fact, current-data, or basic web search
- REJECT: too vague, malformed, or missing critical context

Request: <input>

Respond as JSON: {
  "route": "...",
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "missing_context": [...] // only if REJECT
}
```

Latency: 200-500ms. Cost: ~$0.0001 per call at Haiku tier.

**Stage 3 — The Prompt fallback (resolves ~2% of requests).**

When Stage 2 returns low confidence (<0.7), escalate to The Prompt with web search. This matches the brain's Layer 6 pattern — Prompt is escalation, not default.

Stage 3 is rare enough that its cost doesn't dominate. Used for genuinely ambiguous requests where reasoning about routing is itself non-trivial.

### Initial simple-handle path set (v1)

Six categories, each with a direct-tool path:

| Category | Detection pattern | Handler |
|---|---|---|
| Weather | 'what's the weather', 'weather in <place>', 'forecast' | Web search to weather page |
| Time/date | 'what time is it', 'what's the date', 'what day' | System clock or web search |
| Currency conversion | '<amount> <currency> to <currency>', 'convert <amount>' | Web search or API |
| Single-fact lookup | 'who is <person>', 'what is <noun>', 'when did <event>' | Web search, return first result |
| Basic web search | 'search for <topic>', 'find <thing>' | Web search, return top 3 results |
| Definition | 'define <word>', 'what does <word> mean' | Dictionary API or web search |

All simple-handle paths return a single response synchronously; no cycle is started.

### Rejection format

```json
{
  "rejection_reason": "too_vague" | "malformed" | "missing_context" | "out_of_scope",
  "missing_context": ["what to build", "target language", "constraints"],
  "suggested_clarification": "What specifically should this script do? Which programming language? Any constraints I should know about?"
}
```

### Log format for evaluator audit

Every triage decision is logged in episodic memory before any downstream action:

```json
{
  "event": "triage_decision",
  "ts": 1716042000000,
  "input": "<raw request text>",
  "input_length": 47,
  "stage": 1 | 2 | 3,
  "route": "loop_worthy" | "simple_lookup" | "reject",
  "confidence": 0.95,
  "reasoning": "matched explicit task verb 'refactor'" | "<llm output>",
  "latency_ms": 0.8,
  "cost_usd": 0.0,
  "outcome": null  // updated post-cycle if loop_worthy
}
```

The `outcome` field is filled in after the cycle completes (or after a simple-handle response is served). The evaluator audits triage by joining triage_decision events with their downstream outcomes: did the loop_worthy routes succeed? Did the simple_lookup routes satisfy the user (proxy: no immediate re-query)? Did rejects come back rephrased and succeed?

### Threshold tuning

v1 ships with default thresholds, the evaluator tunes them:

- **Stage 1 → Stage 2 trigger:** rules return no match OR rules match with ambiguity (multiple patterns match)
- **Stage 2 → Stage 3 trigger:** Stage 2 confidence < 0.7
- **Stage 2 reject threshold:** Stage 2 returns REJECT with confidence > 0.85; otherwise fall to Stage 3 for double-check

These are knobs the evaluator can adjust based on observed false-positive/false-negative rates.

### What we are NOT doing

- **Pure LLM routing.** Stage 2 alone would burn cost on every request including obvious simple lookups. The rules-first cascade catches the easy 70% for free.
- **Pure rules-based.** Brittle to novel phrasing. Stage 2 catches what Stage 1 misses.
- **Embedding-based intent matching.** Requires a labeled corpus we don't have. Could be added in v2 if the LLM stage proves consistently slow.
- **Trained classifier (TF-IDF + logistic regression).** Would be cheaper than Stage 2 but requires labeled training data. v2 candidate after the LLM stage has produced labeled traces from production.
- **Reinforcement learning routing (xRouter-style).** Way out of scope. Reserved for if cost dominates.

### Failure modes this addresses

- **Loop processing trivia** — Stage 1 catches obvious simple lookups before they reach the engine. Per Mavik Labs, the cost of running everything through the full agentic loop is 20-50x more than a lightweight direct response.
- **Rejection misclassification (false rejects of real jobs)** — Stage 3 fallback prevents Stage 2 from rejecting genuinely complex requests it didn't understand.
- **Trivia entering the loop and diluting evaluator signal** — Triage decisions are logged and audited; consistent misclassifications surface as patterns the evaluator tunes against.

---

## Cross-cutting observations

### Cost stack for v1 (estimated, per session)

Assuming typical session = 2 cycles (build + refine):

| Component | Per-session cost | Notes |
|---|---|---|
| Triage (Stage 1) | ~$0.00 | Rules; free |
| Triage (Stage 2, if fires) | ~$0.0001 | One Haiku call |
| Seeder reflection (cycle boundary, 2 cycles = 1 boundary actually) | ~$0.01-0.02 | Sonnet with multi-lens, optional web search |
| Framework (executor) | ~$0.05-0.50 | Cycle work; dominant cost, deployer-controlled |
| Steering brain (typical: framework reasoning, escalations rare) | ~$0.001-0.01 | Most invocations are framework-internal |
| Steering brain Layer 6 (rare, ~5% of sessions) | ~$0.05 | Three Opus passes when it fires |
| Context steward (continuous, Haiku) | ~$0.005 | Polling small model throughout cycle |
| Evaluator Layer 1 (rules) | $0.00 | Free |
| Evaluator Layer 2 (LLM attribution, on anomaly) | ~$0.02 | One Opus call when needed |
| Evaluator Layer 3 (classifier update, periodic) | $0.00 | Background batch |

**Total typical session: ~$0.10-0.60.** The framework cost dominates; everything else is rounding error. This makes sense — the framework is doing the actual work.

### Implementation priority for v1

In order of build:

1. **Triage gate (Stage 1 + Stage 2)** — smallest, contained, lets us test request handling end-to-end without needing the evaluator yet
2. **Memory stores** — schema + write paths + read paths. Required by every other component.
3. **Cycle wrapper / orchestrator** — minimal loop that hands off to framework, captures outputs, stages handoff to next component
4. **Seeder (cold start passthrough + warm-start reflection)** — multi-lens reflection, cycle preparation, stop decision
5. **Steering brain dispatch** — universal trigger interception, framework-default reasoning, Prompt escalation on Layer 6, dispatch lock
6. **Context steward** — continuous monitoring, four intervention types
7. **Evaluator (Layer 1 rules → Layer 2 LLM → Layer 3 classifier)** — scoring, attribution, threshold tuning

This order lets each component be tested in isolation against the prior pieces. The evaluator comes last because it audits everything else.

### What this research changes about the architecture doc

All three TBDs land cleanly without restructuring. Recommended addenda to architecture v0.9:

- TBD-4 marked resolved: SQLite (three tables) + vector store (semantic memory). Schema sketched.
- TBD-2a marked resolved: three-layer hybrid evaluator (rules / LLM / classifier).
- TBD-9 marked resolved: three-stage cascade triage (rules / Haiku / Prompt).
- Reference this document from each TBD entry in section 8.

---

## Sources

All sources accessed 2026-05-18 via DuckDuckGo + URL fetch.

**Academic / surveys:**
- *Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers* (arXiv 2603.07670, Du 2026). Foundational taxonomy and design objectives.
- *AgenTracer: Who Is Inducing Failure in the LLM Agentic Systems?* (arXiv 2509.03312). Small specialized judge model outperforms larger proprietary ones for failure attribution.
- *Which Agent Causes Task Failures and When?* (ICML 2025 spotlight). Who&When benchmark for multi-agent failure attribution.
- *Scaling LLM Test-Time Compute Optimally Can be More Effective than Scaling Parameters* (Snell et al., ICLR 2025). PRM-based reasoning verification.
- *Reflexion* (Shinn et al., NeurIPS 2023). Verbal self-critique in episodic memory.

**Production framework comparisons:**
- Vectorize.io: *Best AI Agent Memory Systems in 2026: 8 Frameworks Compared*. Quick-comparison table for Mem0, Hindsight, Letta, Zep/Graphiti, Cognee, SuperMemory, LangMem, LlamaIndex.
- SurePrompts: *Agent Memory Architectures Compared (2026): Provider, Letta, mem0, RAG, Custom*. Decision framework (3 questions).
- Zylos.ai: *LLM-as-Judge in Production: Agent Reasoning Verification, Self-Correction, and Hallucination Defense (2026)*. Six judge patterns, open-source models, failure modes.

**Engineering patterns:**
- Principia Agentica: *Memory in Agents: Episodic vs Semantic, and the Hybrid That Works*. Implementation patterns + token-budget pseudocode.
- Developers.dev: *Architecting Persistent Memory for AI Agents*. Three pillars (working / episodic / semantic), pattern catalog.
- Mavik Labs: *Agent Routing Strategies in 2026: The Router Is the Product*. Five-layer routing model, cost analysis.
- markaicode.com: *The LLM Router Pattern: Dynamically Switching Models by Task Complexity*. TF-IDF + LR for tiny classifier.
- AWS Prescriptive Guidance: *Workflow for routing*. Classifier-routing pattern in production architecture.

---

*End of research findings. Recommendations ready for architecture v1.0 integration.*
