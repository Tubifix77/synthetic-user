"""PreToolUse hook handler (architecture2.md section 2.9 — action-pattern triggers).

Fires before each tool call. Two responsibilities:
  1. Steward interrupt: if the context steward set the interrupt flag, deny the
     call so the cycle ends at this tool boundary.
  2. Action patterns: match the pending call against the four registered
     patterns (hooks/action_patterns.py). On a match, ask the brain for a verdict
     and map it — proceed → allow, redirect → allow + injected context,
     halt → deny with reason. No match → allow with no LLM call.

FM-19 fail-safe: a crash BEFORE a pattern matched allows (ordinary tools must not
be blocked by a broken handler); a crash AFTER a match denies — the registered
patterns are the irreversible set and fail closed.
"""
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from hooks.state import get_interrupt_flag, in_run, log_hook_event, read_payload

_matched = None  # set once a registered pattern matched; decides the crash direction


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main():
    global _matched
    if not in_run():
        return
    payload = read_payload()
    tool_name = payload.get("tool_name", "")
    session_id = payload.get("session_id", "")

    # Steward interrupt: deny the next tool call to end the cycle cleanly.
    if get_interrupt_flag():
        log_hook_event({"hook": "PreToolUse", "session_id": session_id, "action": "interrupt", "tool": tool_name})
        _deny("Synthetic-user steward requested cycle interrupt.")
        return

    from hooks.action_patterns import hook_output_for, is_director_call, match_action
    tool_input = payload.get("tool_input") or {}

    # A director call: set its timeout so the tool can never cut the director off
    # before its own deadline (config.DIRECTOR_TOOL_TIMEOUT_MS), whatever Claude
    # asked for. Never judged as an action pattern — the question text may well
    # mention DDL or `pip install`. Permission comes from --allowedTools, so no
    # permissionDecision here.
    if is_director_call(tool_name, tool_input):
        from synthetic_user.config import DIRECTOR_TOOL_TIMEOUT_MS
        log_hook_event({"hook": "PreToolUse", "session_id": session_id, "action": "director_timeout_set",
                        "tool": tool_name, "requested": tool_input.get("timeout"),
                        "timeout": DIRECTOR_TOOL_TIMEOUT_MS})
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {**tool_input, "timeout": DIRECTOR_TOOL_TIMEOUT_MS},
        }}))
        return

    match = match_action(tool_name, tool_input, payload.get("cwd", ""))
    if match is None:
        log_hook_event({"hook": "PreToolUse", "session_id": session_id, "action": "allow", "tool": tool_name})
        return  # exit 0, no output: the tool call proceeds
    _matched = match

    from hooks.router import read_first_user_text
    from synthetic_user.brain import judge_action
    verdict = judge_action(
        match.pattern, match.summary,
        tool_call=json.dumps({"tool": tool_name, "input": payload.get("tool_input")})[:1500],
        goal=read_first_user_text(payload.get("transcript_path", "")),
    )
    output = hook_output_for(match, verdict)
    log_hook_event({
        "hook": "PreToolUse",
        "session_id": session_id,
        "action": "action_pattern",
        "tool": tool_name,
        "pattern": match.pattern,
        "summary": match.summary[:300],
        "verdict": verdict["verdict"],
        "reason": verdict["reason"][:300],
        "decision": (output or {}).get("hookSpecificOutput", {}).get("permissionDecision", "allow"),
    })
    if output is not None:
        print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        if _matched is not None:
            # Registered action + handler fault → fail closed.
            try:
                log_hook_event({"hook": "PreToolUse", "action": "handler_fault_deny",
                                "pattern": _matched.pattern, "error": repr(exc)[:300]})
            except Exception:  # noqa: BLE001
                pass
            _deny(f"Synthetic-user director unavailable for a registered action "
                  f"({_matched.pattern}); failing closed.")
        # Otherwise: FM-19 safe direction for ordinary tools = allow (exit 0, no output).
        sys.exit(0)
