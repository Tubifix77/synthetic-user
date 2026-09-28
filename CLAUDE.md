# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is
A closed-loop control system that wraps Claude Code (the executor) with the
human-operator roles that normally sit around an agentic loop: triage,
seeding/direction, in-flight steering, context stewardship, and post-hoc
evaluation.

**The build is complete.** All 17 acceptance scenarios pass against a live
`claude -p` subprocess (16 and 17, for the PreToolUse guardrails, landed in the
2026-09-28 hardening pass). A local web UI + `synth` CLI front the system. The design phase (v1.5) is locked; what exists now is a
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
  hooks + a director command, not subagents or an MCP server — see §12.2, §12.9).
- `architecture2.md` section 0 — vocabulary (cycle / turn / Run mapping).
- `OPERATIONS.md` — install, authenticate, run the suite, drive a Run.

## Commands
Run from the repo root. **No linter or formatter is configured** — `pytest` is the
only tooling; don't add or assume a lint step.

- **Install** (editable + test deps): `pip install -e ".[dev]"`
- **One-shot setup/verify**: `python bootstrap.py` — checks prereqs, installs,
  verifies `claude` auth, smoke-tests headless exec, then runs the fast suite,
  stopping on the first failure with an actionable message.
- **Auth precondition** (the wrapper drives the CLI headlessly — get this green
  first): `claude -p "reply with OK" --output-format json` → want `is_error:false`.
- **Fast tests** (pure Python, no LLM, seconds — scenarios 1/2/9/15 + unit tests
  for the halt router, action patterns, hook gating, model routing, permissions,
  subprocess hygiene): `python -m pytest -m "not integration"`
- **Integration tests** (drive a live `claude -p`; minutes each; cost real plan
  usage; need a logged-in CLI): `python -m pytest -m integration`
- **A single scenario**: `python -m pytest tests/test_scenario_07.py -v`
- **The whole suite** (a clean run is the 17 scenarios passing): `python -m pytest`
- **Run it like a user**: `python -m synthetic_user` (web UI on localhost:8765),
  `python -m synthetic_user doctor`, `python -m synthetic_user run "goal"`.
  `start.bat` is the Windows double-click launcher. (`synth` is the same entry
  point but its Scripts dir is often not on PATH on Windows.)

After editing `.claude/settings.json`, fully restart any `claude`
session so it re-reads them. Test-only env knobs that force rare paths
deterministically (e.g. `SYNTH_REACTIVE_TEST=1`) are listed in OPERATIONS.md §7.

## How the system actually attaches to Claude Code (as built)
The wrapper drives the official `claude` CLI headlessly (`claude -p`) and
intercepts the framework through two mechanisms it already exposes:

- **Hooks** (`.claude/settings.json`): `SessionStart` injects operating
  instructions, `Stop` runs the halt-language router (reactive steering),
  `PreToolUse` feeds action-pattern triggers, `PostToolUse` feeds the context
  steward. Hook commands are anchored on `$CLAUDE_PROJECT_DIR`
  (`python "$CLAUDE_PROJECT_DIR/hooks/<handler>.py"`) — hooks run in the session's
  *current* directory, so a CWD-relative command breaks after the framework `cd`s,
  and a hook that can't start fails open (scenario 17).
- **A director command** (`python -m synthetic_user.director "question" "context"`,
  run through Claude's Bash tool): the proactive steering path — the framework
  runs it instead of stopping to ask, the brain answers on stdout, the framework
  continues in the same turn. It was an MCP server until company policy allowed
  only official MCP servers (§12.9); there is deliberately no `.mcp.json`.

These cover uncorrelated failure modes (if the framework forgets to consult, the
Stop hook still catches halt-language; if halt-language is ambiguous, the consult
path still works). Both verified end-to-end (scenarios 3 and 4).

> Note: the original design (and earlier versions of this file) anticipated the
> control surfaces as Claude Code **subagents** in `.claude/agents/`. The build
> used **hooks + a proactive-steering endpoint** (first an MCP server, now a
> Bash-invoked command) instead — the cleaner integration surface in
> practice. There are no subagents. See §12.2 for the reasoning.

## Code map (concern → file)
Two cross-cutting invariants explain most of the wiring, and neither is visible
from a single file:
- **One Run = one `claude` session**, resumed across cycles (`executor.py` holds
  `session_id` and passes `--resume`).
- **The evaluator is the only writer to memory.** Every other component emits
  Decision Reports into a per-Run buffer (`reports.py`); the evaluator drains it
  to `memory.py` at each cycle close. Do not write memory from anywhere else.

The control wrapper is `synthetic_user/` (plain modules that shell out to
`claude -p` for their own reasoning passes). `hooks/` is the
Claude Code interception surface — **path-invoked, never imported** (hence absent
from the installed package).

| Concern | File |
|---|---|
| Run loop: triage → seeder → execute → evaluate → reflect; owns state + buffer | `synthetic_user/orchestrator.py` |
| Request router (Stage-1 rule + Stage-2 classifier) | `synthetic_user/triage.py` |
| Cycle-boundary reflection, cold start, stop codes | `synthetic_user/seeder.py` |
| Steering brain: dispatch + triple-check escalation (`_is_hard_call`) | `synthetic_user/brain.py` |
| 3-layer eval + multi-hat panel; **sole memory writer** | `synthetic_user/evaluator.py` |
| Decision Report store + `query_reports` (in-process v1) | `synthetic_user/memory.py` |
| Decision Report schema + per-Run buffer | `synthetic_user/reports.py` |
| `ClaudeCodeExecutor`: drives `claude -p`, resumes the session | `synthetic_user/executor.py` |
| Shared vocabulary: Run, Cycle, Route, StopCode | `synthetic_user/types.py` |
| Tunables, per-role model tiers (`model_for` — the only place a model is chosen), executor permission grants | `synthetic_user/config.py` |
| Reactive steering: Stop-hook + halt-language classifier | `hooks/stop_handler.py`, `hooks/router.py` |
| Steward (token tracking) + action-pattern triggers | `hooks/post_tool_use_handler.py`, `hooks/pre_tool_use_handler.py` |
| Per-Run hook IPC: hooks log, dispatch lock, token counter | `hooks/state.py` |
| Proactive steering: the director command (fail-safe answers, off switch, deadline) | `synthetic_user/director.py` |
| Guardrails: the 4 PreToolUse action patterns + verdict mapping | `hooks/action_patterns.py`, `brain.judge_action` |
| Front end: Run driver + record, setup checks, CLI, web UI | `synthetic_user/runner.py`, `doctor.py`, `cli.py`, `ui/` |

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
  via the hooks and the director command above.

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
- **No MCP servers** — company policy allows only official ones. Don't add a
  `.mcp.json` (`doctor` warns, `tests/test_no_mcp_server.py` fails). The
  director is `synthetic_user/director.py`, run via Bash.
- Director timeouts nest: brain passes → `DIRECTOR_DEADLINE_S` (300 s, then an
  explicit "director unavailable") → `DIRECTOR_TOOL_TIMEOUT_MS` (480 s, which the
  PreToolUse hook sets on every director call via `updatedInput`) → the CLI's
  Bash max (600 s; the executor guarantees it and strips
  `CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS`). Keep each layer outlasting the one
  inside it — a director killed mid-answer returns nothing at all.
- `SYNTH_DIRECTOR_DISABLED=1` is the authoritative way to switch the proactive
  path off (scenario 3); a Bash deny rule is only a safety net.
- `PostToolUse` only fires for tools that actually execute — permission-blocked
  tools never trigger it, so the steward sees nothing for those.
- `pyproject.toml` declares `synthetic_user` (+ `synthetic_user.ui`) as the only
  packages; `hooks/` is path-invoked, not imported.
- Hooks fire for EVERY session in this folder (yours too). Handlers must stay inert
  unless `SYNTH_SESSION_DIR` is set (`hooks/state.in_run()`).
- Every internal `claude -p` needs `stdin=subprocess.DEVNULL` (`claude -p` waits
  on any inherited pipe — it hung the old MCP server) and `encoding="utf-8"` (Windows defaults to cp1252).
  Fast tests enforce the first.
- Bypass mode can be disabled by org policy: `--dangerously-skip-permissions` then
  silently becomes acceptEdits. The executor grants tools explicitly via
  `--allowedTools` (`config.EXECUTOR_ALLOWED_TOOLS`); keep those grants narrow.
- Word injected instructions (SessionStart) as honest descriptions, not commands:
  "no human at the keyboard / you MUST / authoritative" reads as a prompt
  injection and current models refuse it.
- No model IDs outside `config.py` — `tests/test_model_tiers.py` fails otherwise.

## Status
- Design: v1.5, complete. Tags v1.2-locked, v1.3, v1.4, v1.5 on origin.
- Build: **all 17 scenarios pass.** v1 stand-ins behind stable interfaces:
  in-process memory, keyword-triggered brain escalation, heuristic seeder
  reflection, and a Layer-1 evaluator that only checks a deliverable exists (so
  the Layer-2 panel rarely fires on its own). Upgrades are swaps, not rewrites;
  see §12.4. §12.8 records the 2026-09-28 hardening pass.
- `test_scenario_03` (reactive Stop-hook) — formerly known-flaky, now **resolved
  and deterministic**: it drives the executor directly (bypassing live-LLM
  triage), dictates the exact clarifying question, and asserts both
  `halt_intercepted` and `allow_passthrough`. The halt regex is pinned by a fast
  unit test (`tests/test_router_halt_patterns.py`) so the false-positive
  regression cannot silently return. See §12.7.
