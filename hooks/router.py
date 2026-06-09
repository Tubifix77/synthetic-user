"""Stop-hook router (architecture2.md section 2.9).

Stage 1: regex classifier. If the final assistant message looks like a halt
(CC asked the user something instead of calling consult_director), return True.
Real Stage 2 would use Haiku for ambiguous cases; Stage 1 catches the clear ones.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# Patterns that indicate CC stopped to ask the user rather than completing.
# Ordered from most to least specific.
_HALT_PATTERNS = [
    r"could you (?:please )?(?:clarify|confirm|specify|tell me|let me know|provide)",
    r"(?:before I (?:proceed|continue|start)|before proceeding)",
    r"I (?:need|would like) (?:to (?:ask|know|confirm|clarify)|more information|your (?:input|confirmation|clarification))",
    r"(?:please )?(?:let me know|tell me) (?:what|which|how|if|whether)",
    r"what (?:would you like|do you (?:want|prefer))",
    r"(?:can|could) you (?:clarify|confirm|specify|tell me|let me know|provide)",
    r"I have (?:a (?:few )?)?questions?",
    r"I(?:'d| would) (?:need|like) (?:to know|clarification|more details)",
]

_HALT_RE = re.compile("|".join(_HALT_PATTERNS), re.IGNORECASE)


def read_last_assistant_text(transcript_path: str) -> str:
    """Return the text of the last assistant message in the CC transcript JSONL."""
    path = Path(transcript_path)
    if not path.exists():
        return ""
    last_text = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Handle both bare messages and envelope-wrapped ones.
        message = msg.get("message", msg)
        if message.get("role") != "assistant":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            last_text = content
        elif isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            last_text = "\n".join(parts)
    return last_text


def is_halt(text: str) -> bool:
    """Return True if the text looks like CC is halting to ask the user."""
    return bool(_HALT_RE.search(text))


def read_tool_calls_from_transcript(transcript_path: str) -> list[dict]:
    """Return all tool-use blocks from the transcript, newest-turn-last.

    Each entry has at minimum: ``tool_name``, ``turn_index``, and ``input``
    (the dict passed to the tool).  Useful for verifying that a named tool
    (e.g. ``consult_director``) was actually invoked during the run without
    relying solely on the MCP-server hook log.
    """
    path = Path(transcript_path)
    if not path.exists():
        return []
    calls: list[dict] = []
    turn_index = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = msg.get("message", msg)
        if message.get("role") != "assistant":
            if message.get("role") == "user":
                turn_index += 1
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                calls.append({
                    "tool_name": block.get("name", ""),
                    "tool_use_id": block.get("id", ""),
                    "input": block.get("input", {}),
                    "turn_index": turn_index,
                })
    return calls
