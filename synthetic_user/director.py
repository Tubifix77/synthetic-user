"""consult_director as a command (architecture2.md §2.9 — proactive brain entry).

    python -m synthetic_user.director "question" ["context"]
    python -m synthetic_user.director  < question-then-blank-line-then-context

Claude runs this through its Bash tool instead of stopping to ask the user
(SessionStart tells it how). The command blocks while the brain answers, and the
answer is its stdout, so Claude continues in the same turn. It replaced the
FastMCP server of the same name: company policy allows only official MCP servers
(§12.9).

Always exits 0 with an answer on stdout — a verdict, or an explicit "Director
unavailable …" (FM-19). SYNTH_DIRECTOR_DISABLED=1 is the authoritative off
switch (scenario 3); the executor's Bash deny rule is only a safety net.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from hooks.state import in_run, log_hook_event, set_dispatch_lock  # noqa: E402
from synthetic_user.config import DIRECTOR_DEADLINE_S  # noqa: E402

UNAVAILABLE = ("Director unavailable: {why}. Use your best judgement, continue, and state the "
               "assumption you made in your final report.")


def read_question(argv: list[str], stdin) -> tuple[str, str]:
    """Question and context from arguments, or else from stdin (question, blank line, context)."""
    if argv:
        return argv[0].strip(), " ".join(argv[1:]).strip()
    text = "" if stdin is None or stdin.isatty() else stdin.read()
    question, _, context = text.strip().partition("\n\n")
    return question.strip(), context.strip()


def answer(question: str, context: str) -> tuple[str, str]:
    """(stdout text, logged action)."""
    if os.environ.get("SYNTH_DIRECTOR_DISABLED") == "1":
        return UNAVAILABLE.format(why="the director is switched off for this Run"), "director_disabled"
    if not in_run():
        return UNAVAILABLE.format(why="no synthetic-user Run is active"), "no_run"
    if not question:
        return UNAVAILABLE.format(why="no question was given"), "no_question"
    from synthetic_user.brain import dispatch
    verdict = dispatch(question, context, deadline=time.monotonic() + DIRECTOR_DEADLINE_S)
    if not verdict or verdict.startswith("[brain"):
        return UNAVAILABLE.format(why=f"the brain could not answer ({verdict[:160] or 'empty reply'})"), \
            "director_unavailable"
    # The Stop hook must not answer this same question again at the end of the turn.
    set_dispatch_lock(True)
    return verdict, "proactive_dispatch"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        question, context = read_question(sys.argv[1:] if argv is None else argv, sys.stdin)
        text, action = answer(question, context)
    except Exception as exc:  # noqa: BLE001 — never a traceback in Claude's face
        question, text, action = "", UNAVAILABLE.format(why=f"internal error: {exc!r}"[:200]), "director_error"
    try:
        log_hook_event({"hook": "consult_director", "action": action,
                        "question_preview": question[:200], "verdict_preview": text[:200]})
    except Exception:  # noqa: BLE001
        pass
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
