"""Stop hook handler (architecture2.md section 2.9 — reactive brain entry + evaluator entry).

Fires at the end of every CC turn. Two responsibilities:
  1. Evaluator entry: if CC completed cleanly, return nothing (orchestrator handles it).
  2. Reactive brain entry: if CC halted to ask the user, classify + invoke brain +
     return additionalContext so CC continues in the same session.

stop_hook_active guard: CC sets this True if the Stop hook already blocked this
iteration. We must not block again (infinite-loop guard; CC enforces max 8).
"""
import json
import sys

sys.path.insert(0, "D:/AI/Synthetic")
from hooks.router import is_halt, read_last_assistant_text
from hooks.state import log_hook_event, get_dispatch_lock, clear_dispatch_lock

sys.path.insert(0, "D:/AI/Synthetic")
from synthetic_user.brain import dispatch as brain_dispatch


def main():
    payload = json.load(sys.stdin)
    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")
    already_blocked = payload.get("stop_hook_active", False)

    # If we already blocked this turn, let it through to avoid an infinite loop.
    if already_blocked:
        log_hook_event({"hook": "Stop", "session_id": session_id, "action": "allow_passthrough", "reason": "stop_hook_active"})
        sys.exit(0)

    # Dispatch lock: if consult_director already fired this turn, don't double-fire.
    if get_dispatch_lock():
        clear_dispatch_lock()  # reset for the next turn
        log_hook_event({"hook": "Stop", "session_id": session_id, "action": "lock_skipped", "reason": "consult_director already dispatched this turn"})
        sys.exit(0)

    last_text = read_last_assistant_text(transcript_path)
    halt = is_halt(last_text)

    if not halt:
        # Clean completion — let evaluator + seeder handle it from the orchestrator.
        log_hook_event({"hook": "Stop", "session_id": session_id, "action": "completion"})
        sys.exit(0)

    # Halt detected: invoke brain, inject answer, block the stop so CC continues.
    brain_answer = brain_dispatch(last_text)
    log_hook_event({
        "hook": "Stop",
        "session_id": session_id,
        "action": "halt_intercepted",
        "halt_text_preview": last_text[:200],
        "brain_answer_preview": brain_answer[:200],
    })

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": brain_answer,
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        # FM-19: safe direction on crash = allow CC to stop (exit 0, no block).
        sys.exit(0)
