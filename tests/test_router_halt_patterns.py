"""Fast, deterministic unit coverage for the Stop-hook halt classifier
(hooks/router.py :: is_halt).

No LLM, runs in milliseconds. This pins the discrimination that the regex must
hold, so the false-positive regression that prompted it (a widened pattern that
flagged 8/10 completion sentences as halts) cannot silently return:

  - HALT_UTTERANCES      — genuine halt-language; every one MUST be a halt.
  - COMPLETION_UTTERANCES — ordinary completion prose that merely contains words
                            like "what / should / clarify / which / confirm" in a
                            non-questioning way; NONE may be a halt.

If you change the halt patterns, run `pytest tests/test_router_halt_patterns.py`
(or `python tests/test_router_halt_patterns.py` for the discrimination table).
"""
import sys
from pathlib import Path

import pytest

# Allow `python tests/test_router_halt_patterns.py` (for the table) as well as
# pytest, which already puts the repo root on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hooks.router import is_halt

# Genuine halt-language: CC stopping to ask the operator for clarification/input.
HALT_UTTERANCES = [
    "What should the function return?",
    "What should it do with an empty list?",
    "What format should the timestamps be in?",
    "What transformation should process_list apply to each item?",
    "Which sorting order do you want, ascending or descending?",
    "How should the function handle missing keys?",
    "Could you clarify what transformation the function should apply to each item?",
    "Can you confirm the expected output format?",
    "Would you like me to handle negative numbers as well?",
    "Do you want the results written to a file or printed?",
    "Should I use recursion or iteration here?",
    "Can I assume the input list is already sorted?",
    "Before I proceed, what database should I target?",
    "I need more information about the input schema before continuing.",
    "I'd need to know the expected error behavior first.",
    "Please let me know whether to overwrite the existing file.",
    "Let me know which Python version to target.",
    "I have a question about the expected behavior for duplicates.",
    # multi-sentence: narration followed by the actual question.
    "I've drafted the structure. What should the return type be?",
]

# Completion prose that must NOT be classified as a halt. Each deliberately
# contains halt-adjacent words (what/should/clarify/which/confirm/specify/
# question) in a declarative, non-questioning construction.
COMPLETION_UTTERANCES = [
    "Here is what the function should return for each input.",
    "I have implemented it; let me explain what each parameter should contain.",
    "The docstring documents what the output should look like.",
    "The tests verify what the result should be for edge cases.",
    "I added a comment explaining what the caller should expect.",
    "This determines which branch runs at runtime.",
    "I've clarified the logic in the comments.",
    "The function confirms the input is valid before processing.",
    "I should note that the function assumes sorted input.",
    "The README now describes what users should run to get started.",
    "Which approach to use is documented in the design notes.",
    "I confirmed the tests pass and the build is green.",
    "The validator specifies which fields are required.",
    "I've finished and clarified the edge cases in the tests.",
    "What the function does should be clear from its name.",
    "Let me clarify what the function does: it sorts the list in place.",
    "Should the need arise, the function logs a warning and continues.",
    "I'll let you know via the return value if validation fails.",
    "The config determines what should happen on error.",
    "Done. The function reverses the list line by line.",
]


@pytest.mark.parametrize("text", HALT_UTTERANCES)
def test_halt_utterances_are_detected(text):
    assert is_halt(text), f"halt-language not detected: {text!r}"


@pytest.mark.parametrize("text", COMPLETION_UTTERANCES)
def test_completion_utterances_are_not_halts(text):
    assert not is_halt(text), f"completion prose wrongly flagged as halt: {text!r}"


def _print_discrimination_table():
    """Print the match result for every utterance (for manual inspection)."""
    print("\nHALT utterances (all should be True):")
    for t in HALT_UTTERANCES:
        mark = "OK " if is_halt(t) else "MISS"
        print(f"  [{mark}] is_halt={is_halt(t)!s:5} | {t}")
    print("\nCOMPLETION utterances (all should be False):")
    for t in COMPLETION_UTTERANCES:
        mark = "OK " if not is_halt(t) else "FP "
        print(f"  [{mark}] is_halt={is_halt(t)!s:5} | {t}")


if __name__ == "__main__":
    _print_discrimination_table()
