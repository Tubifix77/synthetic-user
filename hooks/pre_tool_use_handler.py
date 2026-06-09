"""PreToolUse hook handler (architecture2.md section 2.9 — action-pattern triggers).

Fires before each tool call. Matches against the four registered action patterns;
on a match invokes the brain for a verdict. Stub (scenarios 3–4): allow all.
Real: git_push_to_public_repo / claim_done / add_dependency / modify_schema patterns.
Also reads the interrupt flag set by the context steward.
"""
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from hooks.state import get_interrupt_flag, log_hook_event


def main():
    payload = json.load(sys.stdin)
    tool_name = payload.get("tool_name", "")
    session_id = payload.get("session_id", "")

    # Steward interrupt: deny the next tool call to end the cycle cleanly.
    if get_interrupt_flag():
        log_hook_event({"hook": "PreToolUse", "session_id": session_id, "action": "interrupt", "tool": tool_name})
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Synthetic-user steward requested cycle interrupt.",
            }
        }))
        return

    # Stub: allow all tool calls (no action-pattern matching yet).
    log_hook_event({"hook": "PreToolUse", "session_id": session_id, "action": "allow", "tool": tool_name})
    # Returning nothing / exit 0 allows the tool call to proceed.


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        # FM-19: safe direction on crash = allow (exit 0, no deny output).
        sys.exit(0)
