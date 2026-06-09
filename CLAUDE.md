# Synthetic User — Claude Code project guide

## What this project is
A closed-loop control system that wraps Claude Code (the executor) with the
human-operator roles that normally sit around an agentic loop: triage,
seeding/direction, in-flight steering, context stewardship, and post-hoc
evaluation.

**The build is complete.** All 15 acceptance scenarios pass against a live
`claude -p` subprocess. The design phase (v1.5) is locked; what exists now is a
working system. Current work is hardening, portability, tooling, and replacing
v1 stand-ins with fuller implementations — not greenfield building.

The full design is in `architecture2.md` — treat sections 0–11 as the source of
truth for *intent*. **Section 12 is the build-status addendum**: it records what
was actually built and where the implementation deliberately diverged from the
design. Where section 12 and the earlier sections describe a concrete mechanism
differently, section 12 describes the running system.

## Repo location
This repo lives at `D:\Projects\synthetic-user` (relocated from the former
`D:\AI\Synthetic`, which no longer exists). It is fully portable — all paths
resolve relative to the repo root — so it also runs from a fresh clone anywhere.
GitHub remote: `github.com/Tubifix77/synthetic-user`.

## Read these first (in order)
- `architecture2.md` section 12 — **build status: what's actually implemented**,
  the substrate divergence, the design→code map, and the v1 stand-ins. Read
  this before assuming anything about how the system is wired.
- `architecture2.md` section 10 — implementation strategy + the 15 acceptance
  scenarios (the original build plan; all done).
- `architecture2.md` section 2.9 — integration surface design (note: built as
  hooks + an MCP server, not subagents — see §12.2).
- `architecture2.md` section 0 — vocabulary (cycle / turn / Run mapping).
- `OPERATIONS.md` — install, authenticate, run the suite, drive a Run.

## How the system actually attaches to Claude Code (as built)
The wrapper drives the official `claude` CLI headlessly (`claude -p`) and
intercepts the framework through two mechanisms it already exposes:

- **Hooks** (`.claude/settings.json`): `SessionStart` injects operating
  instructions, `Stop` runs the halt-language router (reactive steering),
  `PreToolUse` feeds action-pattern triggers, `PostToolUse` feeds the context
  steward. Hook commands are CWD-relative (`python hooks/<handler>.py`); Claude
  Code runs them with CWD = repo root and also sets `CLAUDE_PROJECT_DIR`.
- **An MCP tool** (`.mcp.json` → `director_mcp/consult_director_server.py`):
  `consult_director` is the proactive steering path — the framework calls it
  instead of stopping to ask, the brain answers, the framework continues.

These cover uncorrelated failure modes (if the framework forgets to consult, the
Stop hook still catches halt-language; if halt-language is ambiguous, the consult
path still works). Both verified end-to-end (scenarios 3 and 4).

> Note: the original design (and earlier versions of this file) anticipated the
> control surfaces as Claude Code **subagents** in `.claude/agents/`. The build
> used **hooks + an MCP server** instead — the cleaner integration surface in
> practice. There are no subagents. See §12.2 for the reasoning.

## How we build (non-negotiable)
- Acceptance-test-driven. Write the scenario as an executable test that fails
  meaningfully BEFORE writing production code. Tests are upstream of code.
- Do NOT mock LLM-calling components. The interaction with real model behaviour
  is the thing under test. (This is why the integration tests are slow and cost
  real usage — that's intended.)
- One source of truth: this repo. Code and design live together.
- Paths must stay portable: never hardcode an absolute repo path in code, tests,
  or config. Config is CWD-relative; Python files self-locate via
  `Path(__file__).resolve().parent...`. The relocation test (moving the repo and
  re-running the integration suite) is the standing check for this.

## Substrate (decided)
- Runs on a Claude **subscription / enterprise seat** via the official `claude`
  CLI driven headlessly (`claude -p`). No metered API key; do NOT lift the OAuth
  token into external API calls.
- The EXECUTOR is the main Claude Code thread (`synthetic_user/executor.py`,
  `ClaudeCodeExecutor`). It does the real work and is never a subagent.
- The brain, evaluator, seeder, steward logic live as ordinary Python modules
  in `synthetic_user/` that call `claude -p` for their reasoning passes, invoked
  via the hooks and MCP server above.

## Known compromise on this substrate
- The evaluator's Adversary hat (v1.5) should run on a DIFFERENT model family for
  bias reduction. On subscription-only Claude Code every call is Claude, so we
  get model-TIER diversity (Opus / Sonnet / Haiku), not cross-family. If
  Bedrock/Vertex or another provider's key becomes available, route the
  Adversary hat there — the interface (`synthetic_user/config.py` `MODEL_TIERS`)
  is built so this is a config swap, not a redesign.

## Conventions
- Default to Sonnet for most reasoning roles; reserve Opus for the evaluator's
  deep attribution and the brain's hard calls. Rate limits (not cost) are the
  ceiling on a subscription — design rate-limit-aware and degrade gracefully
  when capped (FM-19).
- Write real Unicode characters in files, never literal backslash-u escape
  sequences.
- Personal / machine-specific settings go in `CLAUDE.local.md` (gitignored).
- CC does the coding and testing in-session; commits/pushes happen from the
  other side (a reviewer commits after checking the work). Don't commit unless
  asked.

## Integration lessons (hard-won — don't re-derive)
- MCP servers register in `.mcp.json` (project root), NOT `.claude/settings.json`.
- MCP tools are not covered by `--dangerously-skip-permissions`; each must be
  explicitly allowed in `settings.json` → `permissions.allow`.
- `PostToolUse` only fires for tools that actually execute — permission-blocked
  tools never trigger it, so the steward sees nothing for those.
- Don't name a local package dir `mcp/` — it shadows the installed `mcp` package
  and crashes the FastMCP import. The server lives in `director_mcp/`.
- `pyproject.toml` declares `synthetic_user` as the sole package; `hooks/` and
  `director_mcp/` are path-invoked, not imported.

## Status
- Design: v1.5, complete. Tags v1.2-locked, v1.3, v1.4, v1.5 on origin.
- Build: **all 15 scenarios pass.** In-process memory and keyword-triggered
  brain escalation are deliberate v1 stand-ins behind stable interfaces (the
  upgrades — SQLite + vector memory, LLM-reflective escalation — are swaps, not
  rewrites; see §12.4).
- Known-flaky: `test_scenario_03` (reactive Stop-hook) depends on headless
  `claude -p` reliably emitting halt-language and is nondeterministic; wiring is
  correct, the prompt needs hardening.
