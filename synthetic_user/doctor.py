"""Setup checks shared by `synth doctor` and the web UI's setup panel.

Each check returns a Check with a plain-language fix, so neither front end needs
to know how the checks work. bootstrap.py remains the stdlib-only first-run
script (it installs the package this module lives in).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from synthetic_user.config import model_for

REPO_ROOT = Path(__file__).resolve().parent.parent

_LOGIN_FIX = (
    "Open a terminal, run `claude`, type /login and finish the browser sign-in "
    "(a Pro/Max/Team/Enterprise account). Then click Re-check."
)


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str = ""
    fix: str = ""
    blocking: bool = True   # False: a warning — shown, but doesn't stop a Run

    def to_dict(self) -> dict:
        return asdict(self)


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=str(REPO_ROOT),
                          stdin=subprocess.DEVNULL)


def check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 11)
    return Check("python", "Python 3.11+", ok, f"Python {v.major}.{v.minor}.{v.micro}",
                 "" if ok else "Install Python 3.11 or newer from python.org.")


def check_git() -> Check:
    ok = shutil.which("git") is not None
    return Check("git", "git", ok, "found" if ok else "not on PATH",
                 "" if ok else "Install git from https://git-scm.com/downloads.")


def check_claude_cli() -> Check:
    if shutil.which("claude") is None:
        return Check("claude_cli", "Claude Code CLI", False, "`claude` is not on PATH",
                     "Install Claude Code (https://claude.com/claude-code), then open a new terminal.")
    try:
        r = _run(["claude", "--version"])
        version = (r.stdout or r.stderr).strip().splitlines()[0]
        return Check("claude_cli", "Claude Code CLI", True, version)
    except Exception as exc:  # noqa: BLE001
        return Check("claude_cli", "Claude Code CLI", False, f"`claude --version` failed: {exc}",
                     "Reinstall Claude Code.")


def check_auth() -> Check:
    try:
        r = _run(["claude", "auth", "status"])
        data = json.loads(r.stdout)
    except Exception as exc:  # noqa: BLE001
        return Check("auth", "Signed in to Claude", False, f"could not read auth status: {exc}", _LOGIN_FIX)
    if not data.get("loggedIn"):
        return Check("auth", "Signed in to Claude", False, "not signed in", _LOGIN_FIX)
    plan = data.get("subscriptionType") or data.get("authMethod") or "signed in"
    return Check("auth", "Signed in to Claude", True, f"signed in ({plan})")


def check_wiring(root: Path = REPO_ROOT) -> Check:
    """The 4 hooks are registered — and no MCP server is. Company policy allows only
    official MCP servers; a project .mcp.json would also bring back Claude Code's
    "Pending approval" prompt. The director is a command (synthetic_user.director)."""
    try:
        settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        wired = {e for e, groups in settings.get("hooks", {}).items() if groups}
        missing = {"SessionStart", "Stop", "PreToolUse", "PostToolUse"} - wired
    except Exception:  # noqa: BLE001
        return Check("wiring", "Hooks wiring", False, ".claude/settings.json unreadable",
                     "Restore it from git: git checkout -- .claude/settings.json")
    if missing:
        return Check("wiring", "Hooks wiring", False, "hooks missing: " + ", ".join(sorted(missing)),
                     "Restore it from git: git checkout -- .claude/settings.json")
    if (root / ".mcp.json").exists():
        return Check("wiring", "Hooks wiring", False,
                     "a .mcp.json is present — this project must not register an MCP server",
                     "Delete .mcp.json (company policy allows only official MCP servers; "
                     "the director is a command, not an MCP tool).", blocking=False)
    return Check("wiring", "Hooks wiring", True, "4 hooks registered; no MCP server")


def check_headless() -> Check:
    """One tiny live call on the cheapest tier — proves `claude -p` really works."""
    try:
        r = _run(["claude", "-p", "reply with OK", "--model", model_for("triage"),
                  "--output-format", "json"], timeout=90)
        data = json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        return Check("headless", "Headless run works", False, "timed out after 90 s", _LOGIN_FIX)
    except Exception as exc:  # noqa: BLE001
        return Check("headless", "Headless run works", False, f"no usable reply: {exc}", _LOGIN_FIX)
    if data.get("is_error"):
        return Check("headless", "Headless run works", False, str(data.get("result"))[:200], _LOGIN_FIX)
    return Check("headless", "Headless run works", True, f"`claude -p` answered on {model_for('triage')}")


def run_checks(live: bool = False) -> list[Check]:
    """All checks, cheapest first. Stops before live checks once something basic fails."""
    checks = [check_python(), check_git(), check_claude_cli(), check_wiring()]
    if checks[2].ok:
        checks.append(check_auth())
        if live and checks[-1].ok:
            checks.append(check_headless())
    return checks
