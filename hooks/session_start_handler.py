"""SessionStart hook handler (architecture2.md section 2.9).

Fires when the orchestrator opens a session. Injects the consult_director
instruction so CC runs the director command instead of asking the user.
"""
import json
import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from hooks.state import in_run, log_hook_event, read_payload
from synthetic_user.config import DIRECTOR_COMMAND

# Worded as an honest description of the setup, not a command. An earlier
# version ("no human at the keyboard … you MUST … authoritative answer") reads
# exactly like a prompt injection, and newer models rightly refused to act on it
# — which silently disabled the proactive steering path (scenario 4).
CONSULT_DIRECTOR_INSTRUCTION = f"""
About this session: it was started by synthetic-user, an automation the user set up
to run Claude Code unattended (this project's .claude/settings.json and the
synthetic_user package). The user is not watching this session, so a question
written in your reply would go unanswered. Instead, the user provided a director
command as their stand-in. When you would stop to ask the user something, run it
with the Bash tool, passing the question and any relevant context:

    {DIRECTOR_COMMAND} "<your question>" "<relevant context>"

It prints the answer (it can take a few minutes on hard questions); continue using
it as the user's guidance. If it says "Director unavailable", use your best
judgement and state your assumption in the final report. Your own judgement always
applies — if an answer looks unsafe or clearly wrong, don't follow it; say so.
Some tools are not permitted here. If a tool call is denied, nobody can approve it:
carry on without that tool and note in your final report what you could not do or
verify.
""".strip()


def main():
    if not in_run():
        return
    payload = read_payload()
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
