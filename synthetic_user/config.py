"""Build-time constants. See architecture2.md sections 2.5, 2.7, 8."""
SCORE_THRESHOLD = 0.70          # evaluator Layer 1 pass bar (tunable; section 2.5)
STEWARD_COMPACT_THRESHOLD = 0.60  # fraction of counted tokens (section 2.7)
MAX_CYCLES_PER_RUN = 25         # safety bound; real stop is the seeder

# Model tiers per role (names only; wired when components call CC). Section 2.5/8.
MODEL_TIERS = {
    "triage": "haiku",
    "steward": "haiku",
    "seeder": "sonnet",
    "director": "sonnet",
    "evaluator_attribution": "opus",
    "hat_correctness": "sonnet",
    "hat_adversary": "sonnet",      # SHOULD be a different family; subscription = tier-only (see CLAUDE.md)
    "hat_user_intent": "sonnet",
}
