"""PostToolUse hook handler (architecture2.md section 2.9 — context steward monitor).

Fires after each tool call. Responsibilities:
  1. Update the running token-estimate counter (tool result size ÷ 4).
  2. Evaluate the 60% compact threshold (or SYNTH_COMPACT_THRESHOLD_TOKENS override).
  3. If threshold crossed: log suggest_compact and return additionalContext so CC
     self-summarises in-turn (preservation guidance).
  4. Log a routine ping on every call regardless.

Threshold env-var override (for testing):
  SYNTH_COMPACT_THRESHOLD_TOKENS=<int>  — override the default 120000-token threshold.

architecture2.md section 2.7: steward intervenes before CC's autocompact (~80% of
context), placing the suggest_compact threshold at ~60% of our counted tokens.
Default context size assumed: 200,000 tokens → 60% = 120,000 tokens.
"""
import json
import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from hooks.state import add_counted_tokens, log_hook_event

# Default threshold: 60% of 200k-token context window.
_DEFAULT_THRESHOLD = 120_000

_PRESERVATION_GUIDANCE = (
    "CONTEXT STEWARD INTERVENTION — suggest_compact:\n"
    "Context is filling. Please summarise your working state now:\n"
    "  • Restate the current goal in one sentence.\n"
    "  • List the key decisions made so far (brain verdicts, design choices).\n"
    "  • List files created or modified.\n"
    "  • Note any open questions or next actions.\n"
    "Then continue working. This summary replaces detailed tool history."
)


def _token_threshold() -> int:
    try:
        return int(os.environ.get("SYNTH_COMPACT_THRESHOLD_TOKENS", _DEFAULT_THRESHOLD))
    except ValueError:
        return _DEFAULT_THRESHOLD


def _estimate_tokens(payload: dict) -> int:
    """Rough token estimate: total JSON chars of tool result ÷ 4."""
    tool_resp = payload.get("tool_response", {})
    raw = json.dumps(tool_resp)
    return max(1, len(raw) // 4)


def main():
    payload = json.load(sys.stdin)
    session_id = payload.get("session_id", "")
    tool_name = payload.get("tool_name", "")

    delta = _estimate_tokens(payload)
    total = add_counted_tokens(delta)
    threshold = _token_threshold()

    # Routine ping — always logged.
    log_hook_event({
        "hook": "PostToolUse",
        "session_id": session_id,
        "tool": tool_name,
        "action": "steward_ping",
        "counted_tokens": total,
        "threshold": threshold,
        "delta": delta,
    })

    if total >= threshold:
        log_hook_event({
            "hook": "PostToolUse",
            "session_id": session_id,
            "tool": tool_name,
            "action": "suggest_compact",
            "counted_tokens": total,
            "threshold": threshold,
            "preservation_guidance": _PRESERVATION_GUIDANCE,
        })
        # Inject preservation guidance into CC's context.
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": _PRESERVATION_GUIDANCE,
            }
        }))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        # FM-19: safe direction on crash = skip this steward update (exit 0).
        sys.exit(0)
