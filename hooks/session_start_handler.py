"""SessionStart hook handler (architecture2.md section 2.9).

Fires when the orchestrator opens a session. Injects the consult_director
instruction so CC calls the MCP tool instead of asking the user.
"""
import json
import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from hooks.state import log_hook_event

CONSULT_DIRECTOR_INSTRUCTION = """
IMPORTANT OPERATING INSTRUCTION — synthetic-user wrapper:
You are running inside a closed-loop autonomous system. There is no human at the
keyboard. When you would normally pause and ask the user a question, you MUST
instead call the `consult_director` MCP tool with your question and relevant
context. The tool will return an authoritative answer from the system director.
Do NOT emit text like "I need to ask..." or "Could you clarify..." and stop.
Always call consult_director first. Continue working with the answer it returns.
""".strip()


def main():
    payload = json.load(sys.stdin)
    session_id = payload.get("session_id")
    log_hook_event({"hook": "SessionStart", "session_id": session_id})

    # SYNTH_REACTIVE_TEST=1: skip the consult_director injection so CC can halt
    # naturally. Used by scenario 3 to exercise the reactive Stop-hook path.
    if os.environ.get("SYNTH_REACTIVE_TEST"):
        log_hook_event({"hook": "SessionStart", "session_id": session_id, "action": "reactive_mode_no_injection"})
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": CONSULT_DIRECTOR_INSTRUCTION,
        }
    }))


if __name__ == "__main__":
    main()
