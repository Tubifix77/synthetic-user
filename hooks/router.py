"""Stop-hook router (architecture2.md section 2.9).

Stage 1: regex classifier. If the final assistant message looks like a halt
(CC asked the user something instead of calling consult_director), return True.
Real Stage 2 would use Haiku for ambiguous cases; Stage 1 catches the clear ones.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Halt detection.
#
# A "halt" is the framework stopping mid-task to ask the operator a question
# instead of completing or calling consult_director. The hard part is telling
# genuine halt-language apart from ordinary completion prose that merely contains
# words like "what", "should", "clarify", or "which" in a declarative sentence
# ("Here is what the function should return.").
#
# The discriminator is INTERROGATIVE STRUCTURE, not loose keyword proximity:
#   1. a sentence that OPENS with an interrogative (wh-word or subject/aux
#      inversion) AND ends with a question mark; or
#   2. a sentence that OPENS with an imperative request ("let me know ...",
#      "tell me ..."); or
#   3. an inherently halt-like request phrase ("could you clarify ...", "before
#      I proceed", "I need more information", "I have a question") anywhere.
#
# The fast corpus in tests/test_router_halt_patterns.py pins this discrimination
# (every halt utterance matches; no completion sentence does).
# ---------------------------------------------------------------------------

# Optional leading discourse markers ("So, what ...?", "Okay — could you ...?").
_LEAD = r"(?:so|okay|ok|alright|also|and|but|now|well|hmm)?[\s,—-]*"

# A sentence that OPENS like a question to the user. Only counts as a halt when
# the sentence also ends with "?" (verified separately in is_halt), so the loose
# wh-words can't fire on declarative prose.
_INTERROGATIVE_OPENER = re.compile(
    _LEAD + r"(?:"
    r"what|which|when|where|who|whom|why|how"            # wh-questions
    r"|could you|can you|would you|will you"              # polite requests
    r"|do you|did you|are you|is it"                      # yes/no to the user
    r"|should i|should we|shall i|shall we|may i|can i"   # deferring a choice
    r")\b",
    re.IGNORECASE,
)

# A sentence that OPENS with an imperative request for input. Anchored to the
# sentence start so "the logs tell me what failed" (declarative) does not fire.
_IMPERATIVE_OPENER = re.compile(
    _LEAD + r"(?:please |kindly )?(?:let me know|tell me)\b",
    re.IGNORECASE,
)

# Phrases that are inherently a request for the operator's input — halt-like
# wherever they occur, because they are not ordinary completion prose. Each verb
# is anchored to its request frame ("could you clarify", not bare "clarified").
_REQUEST_RE = re.compile(
    r"\bbefore (?:I|we) (?:proceed|continue|start|begin|move on|go ahead)\b"
    r"|\bI(?:'?d| would)? (?:need|require) "
    r"(?:to know|more (?:information|detail|details|context|clarity)|clarification"
    r"|your (?:input|confirmation|guidance|clarification|direction|decision))\b"
    r"|\b(?:could|can) you (?:please )?"
    r"(?:clarify|confirm|specify|tell me|let me know|provide|elaborate)\b"
    r"|\b(?:please|kindly) (?:let me know|clarify|confirm|specify)\b"
    r"|\bI have (?:an?|a few|a couple of|some)? ?questions?\b",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-ish fragments on terminators and newlines."""
    parts = re.split(r"(?<=[.!?])\s+|[\r\n]+", text.strip())
    return [p.strip() for p in parts if p.strip()]


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
    """Return True if ``text`` is genuine halt-language — a question or an explicit
    request for the operator's input — rather than declarative completion prose.

    Discrimination is by interrogative STRUCTURE (see the module-level notes and
    the corpus in tests/test_router_halt_patterns.py), not loose keyword match,
    so a completion like "Here is what the function should return." does not fire.
    """
    if not text or not text.strip():
        return False
    # (3) Inherently halt-like request phrases, anywhere in the text.
    if _REQUEST_RE.search(text):
        return True
    # (1)/(2) Otherwise require interrogative/imperative structure per sentence.
    for sentence in _split_sentences(text):
        if _IMPERATIVE_OPENER.match(sentence):
            return True
        if sentence.endswith("?") and _INTERROGATIVE_OPENER.match(sentence):
            return True
    return False


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
