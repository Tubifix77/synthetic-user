"""consult_director MCP server (architecture2.md section 2.9 — proactive brain entry).

CC is instructed at SessionStart to call this tool instead of asking the user.
The call blocks synchronously; the brain answers; CC reads the result and continues.

Stub (scenarios 3–4): brain_stub.answer() returns a generic proceed-with-defaults
verdict. Real: triple-check lock + The Prompt invocation for hard calls.

NOTE: This file lives in director_mcp/ (not mcp/) to avoid shadowing the installed
`mcp` Python package.
"""
import sys

sys.path.insert(0, "D:/AI/Synthetic")

from mcp.server.fastmcp import FastMCP
from hooks.brain_stub import answer
from hooks.state import log_hook_event

_mcp = FastMCP("synthetic-user")


@_mcp.tool()
def consult_director(question: str, context: str = "") -> str:
    """Consult the synthetic-user director when you need guidance.

    Call this tool INSTEAD of asking the user a question. The director will
    return an authoritative answer; use it to continue your work.

    Args:
        question: The question you would have asked the user.
        context: Relevant context about what you are working on.
    """
    verdict = answer(question)
    log_hook_event({
        "hook": "consult_director",
        "action": "proactive_dispatch",
        "question_preview": question[:200],
        "verdict_preview": verdict[:200],
    })
    return verdict


if __name__ == "__main__":
    _mcp.run()
