"""The executor's explicit permission grants (config.executor_allowed_tools).

Organisation policy can disable bypass mode, which silently turns
`--dangerously-skip-permissions` into acceptEdits. The executor then runs on
explicit allow rules alone, so what those rules grant by default is a security
decision and is pinned here: read-only by default, running code only on opt-in.

FAST TEST — no LLM calls.
"""
from synthetic_user import config


def test_default_grants_are_read_only_plus_the_director(monkeypatch):
    # The director rule is a prefix for one fixed module; nothing else runs Python.
    monkeypatch.delenv("SYNTH_ALLOW_TESTS", raising=False)
    monkeypatch.delenv("SYNTH_EXTRA_ALLOWED_TOOLS", raising=False)
    rules = config.executor_allowed_tools()
    assert f"Bash({config.DIRECTOR_COMMAND}:*)" in rules
    others = [r for r in rules if config.DIRECTOR_COMMAND not in r]
    assert not any("python" in r or "pytest" in r for r in others), rules
    assert "Bash" not in rules and "Bash(*)" not in rules, "never a blanket shell grant"


def test_running_tests_is_opt_in(monkeypatch):
    monkeypatch.setenv("SYNTH_ALLOW_TESTS", "1")
    assert "Bash(python -m pytest:*)" in config.executor_allowed_tools()


def test_extra_rules_are_semicolon_separated(monkeypatch):
    monkeypatch.setenv("SYNTH_EXTRA_ALLOWED_TOOLS", "Bash(npm test:*); Bash(make check)")
    rules = config.executor_allowed_tools()
    assert "Bash(npm test:*)" in rules and "Bash(make check)" in rules


def test_executor_env_keeps_the_director_timeout_budget(monkeypatch, tmp_path):
    # A backgrounded director call returns "moved to background" instead of an
    # answer, and a lower Bash max would cut it short: the executor rules out both.
    from synthetic_user import executor
    monkeypatch.setenv("CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS", "30000")
    monkeypatch.setenv("BASH_MAX_TIMEOUT_MS", "60000")
    env = executor.ClaudeCodeExecutor(project_root=tmp_path).build_env()
    assert "CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS" not in env
    assert int(env["BASH_MAX_TIMEOUT_MS"]) >= config.DIRECTOR_TOOL_TIMEOUT_MS
    assert executor._CC_TIMEOUT * 1000 > config.DIRECTOR_TOOL_TIMEOUT_MS, "a turn must outlast a director call"
