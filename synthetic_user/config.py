"""Build-time constants. See architecture2.md sections 2.5, 2.7, 8."""
import os

SCORE_THRESHOLD = 0.70          # evaluator Layer 1 pass bar (tunable; section 2.5)
STEWARD_COMPACT_THRESHOLD = 0.60  # fraction of counted tokens (section 2.7)
MAX_CYCLES_PER_RUN = 25         # safety bound; real stop is the seeder

# Tier aliases → concrete model IDs. Bump these when a newer model in the family
# ships; every role on that tier follows.
MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5-5",
}

# Model tier per role. This is the ONLY place a role's model is chosen: every
# `claude -p` call resolves its model through model_for(). Section 2.5/8.
# Rate limits are the ceiling on a subscription, so everything defaults to
# Sonnet/Haiku; move a role to "opus" only when it has earned it.
# Components without an LLM pass yet (steward analysis, seeder reflection,
# evaluator attribution) get a role here when they gain one.
MODEL_TIERS = {
    "executor": "sonnet",           # the framework doing the real work (claude -p main thread)
    "triage": "haiku",              # Stage-2 request classifier
    "director": "sonnet",           # brain: routine answers + action-pattern verdicts
    "director_hard_call": "haiku",  # brain triple-check passes (latency-bound: CC blocks on it)
    "hat_correctness": "sonnet",
    "hat_adversary": "haiku",       # SHOULD be a different family; subscription = tier-only (see CLAUDE.md)
    "hat_user_intent": "sonnet",
    "escape_audit": "haiku",        # FM-18 post-hoc dispatch-escape classifier
}


# The proactive steering path: Claude runs this through Bash instead of asking the
# user (company policy allows only official MCP servers, so it is not an MCP tool).
DIRECTOR_COMMAND = "python -m synthetic_user.director"
# Time budget, outermost last — each layer must outlast the one inside it, or a
# director call is killed mid-answer (a new failure mode, since the CLI then
# returns no answer at all):
#   brain passes (≤120 s each) → DIRECTOR_DEADLINE_S, after which the director
#   answers "unavailable" → DIRECTOR_TOOL_TIMEOUT_MS, which the PreToolUse hook
#   sets on every director call whatever Claude asked for → the CLI's Bash max
#   (600 000 ms unless BASH_MAX_TIMEOUT_MS; the executor guarantees at least that).
DIRECTOR_DEADLINE_S = 300
DIRECTOR_TOOL_TIMEOUT_MS = 480_000

# Permission rules granted to the executor's `claude -p`. Organisation policy can
# disable bypass mode, and then `--dangerously-skip-permissions` silently degrades
# to acceptEdits: file edits still go through, but every other tool call is
# denied unless one of these rules allows it (nobody is there to approve).
EXECUTOR_ALLOWED_TOOLS = [
    f"Bash({DIRECTOR_COMMAND}:*)",         # the proactive steering path
    f"PowerShell({DIRECTOR_COMMAND}:*)",   # same, if Claude picks PowerShell
    "Bash(ls:*)",
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
]
# Opt-in per Run (SYNTH_ALLOW_TESTS=1): running tests executes code the agent wrote.
TEST_RUN_TOOLS = [
    "Bash(python -m pytest:*)",
    "Bash(py -m pytest:*)",
    "Bash(pytest:*)",
]


def executor_allowed_tools() -> list[str]:
    """Rules for this Run: the base set, tests if opted in, plus any extra rules
    from SYNTH_EXTRA_ALLOWED_TOOLS (semicolon-separated, e.g. "Bash(npm test:*)")."""
    rules = list(EXECUTOR_ALLOWED_TOOLS)
    if os.environ.get("SYNTH_ALLOW_TESTS") == "1":
        rules += TEST_RUN_TOOLS
    rules += [r.strip() for r in os.environ.get("SYNTH_EXTRA_ALLOWED_TOOLS", "").split(";") if r.strip()]
    return rules


def model_for(role: str) -> str:
    """Resolve a role to a concrete model ID.

    SYNTH_MODEL_<ROLE> (e.g. SYNTH_MODEL_HAT_ADVERSARY=opus) overrides the tier
    for one role; the value may be a tier alias or a full model ID. Hook handlers
    and the director command inherit the executor's environment, so an override set for
    a Run reaches every component in it.
    """
    choice = os.environ.get(f"SYNTH_MODEL_{role.upper()}") or MODEL_TIERS[role]
    return MODELS.get(choice, choice)
