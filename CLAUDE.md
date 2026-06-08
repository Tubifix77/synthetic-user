# Synthetic User - Claude Code project guide

## What this project is
A closed-loop control system that wraps Claude Code (the executor) with the
human-operator roles that normally sit around an agentic loop: triage,
seeding/direction, in-flight steering, context stewardship, and post-hoc
evaluation. The design phase is complete (v1.5). This repo is now in the BUILD
phase.

The full design is in `architecture2.md` - treat it as the source of truth.
Read it; do not re-derive or contradict it.

## Read these first (in order)
- `architecture2.md` section 10  - Implementation strategy + the 15 acceptance
  scenarios. This is the build plan.
- `architecture2.md` section 2.9 - Integration surface: how the wrapper attaches
  to Claude Code (hooks + the director subagent).
- `architecture2.md` section 0   - Vocabulary (cycle / turn / Run mapping).
- `architecture2.md` sections 2.0, 2.1, 2.5 - the components scenario 1 touches
  (triage, seeder, evaluator).

## How we build (non-negotiable)
- Acceptance-test-driven. Write the scenario as an executable test that fails
  meaningfully BEFORE writing production code. Tests are upstream of code.
- Do NOT mock LLM-calling components. The interaction with real model behaviour
  is the thing under test.
- Build order: scenario 1 (walking skeleton) first; nothing else until
  scenarios 1 and 2 pass. Full order in section 10.4:
  1 -> 2 -> 15 -> 3 -> 4 -> 6 -> 9 -> 10 -> 5 -> 7 -> 8 -> 13 -> 14 -> 11 -> 12.
- One source of truth: this repo. Code and design live together.

## Substrate (decided)
- Runs as a Claude Code subagent flow on a Claude subscription. No metered API
  key: drive the official `claude` tool (headless `claude -p` from the
  orchestrator script). Do NOT lift the OAuth token into external API calls.
- The EXECUTOR is the main Claude Code thread. It does the real work and is
  never a subagent (subagents lose parent context and are weak at coding).
- The CONTROL SURFACES are subagents in `.claude/agents/`: seeder, director
  (the steering brain), the evaluator's multi-hat panel, the steward's
  analysis. These are read/judge/reflect tasks, which subagents do well.
- Mechanical interception is via hooks in `.claude/settings.json`: PostToolUse
  (steward monitor), PreToolUse (action-pattern triggers), Stop (router),
  SessionStart (instructions).
- All project CC config lives in the committed `.claude/` so the flow is
  identical on any machine that clones this repo.

## Known compromise on this substrate
- The evaluator's Adversary hat (v1.5) should run on a DIFFERENT model family
  for bias reduction. On subscription-only Claude Code every subagent is
  Claude, so we get model-TIER diversity (Opus / Sonnet / Haiku), not
  cross-family. If Bedrock/Vertex or another provider's key becomes available,
  route the Adversary hat there. The interface is built so this is a swap, not
  a redesign.

## Conventions
- Default to Sonnet for most subagent roles; reserve Opus for the evaluator's
  deep attribution and the director's hard calls. Rate limits (not cost) are
  the ceiling on a subscription - design rate-limit-aware and degrade
  gracefully when capped (FM-19).
- Write real Unicode characters in files, never literal backslash-u escape
  sequences.
- Personal / machine-specific settings go in `CLAUDE.local.md` (gitignored),
  not here.

## Status
- Design: v1.5, complete. Tags v1.2-locked, v1.3, v1.4, v1.5 on origin.
- Build: not started. First task is scenario 1 (walking skeleton) written as a
  failing acceptance test.
