"""Action-pattern triggers for the PreToolUse hook (architecture2.md §2.9, TBD-2c).

The four registered patterns are the irreversible-by-definition set. A pending
tool call that matches one is gated through the brain regardless of whether the
framework chose to consult; everything else is allowed without an LLM call.

  git_push_to_public_repo — `git push` to a network remote, or `gh repo create --public`
  claim_done              — TodoWrite marking every item completed
  add_dependency          — installing a package, or writing a dependency manifest
  modify_schema           — writing schema/migration files, running migrations or DDL

Matching is pure and deterministic (tests/test_action_patterns.py). The brain's
verdict maps to PreToolUse semantics in hook_output_for().

"Public" is approximated as "not a local path": remote visibility can't be
checked without a network call on every push, so any network remote is gated
and the brain decides.
"""
from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PATTERNS = ("git_push_to_public_repo", "claim_done", "add_dependency", "modify_schema")

_SHELL_TOOLS = {"Bash", "PowerShell"}
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


@dataclass
class ActionMatch:
    pattern: str
    summary: str          # one line for the brain and the hooks log


# ── helpers ─────────────────────────────────────────────────────────────────

def _segments(command: str) -> list[list[str]]:
    """Split a shell line into simple commands (on && || ; |), each tokenised."""
    out = []
    for part in re.split(r"&&|\|\||;|\|", command):
        try:
            tokens = shlex.split(part, posix=True)
        except ValueError:
            tokens = part.split()
        if tokens:
            out.append(tokens)
    return out


def _positionals(tokens: list[str]) -> list[str]:
    return [t for t in tokens if not t.startswith("-")]


def _looks_local(target: str) -> bool:
    return (
        target.startswith(("/", "./", "../", "~", "file://", "\\\\"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", target))
        or target in (".", "..")
    )


# ── git_push_to_public_repo ─────────────────────────────────────────────────

def _git_remote_url(repo_dir: str, remote: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", repo_dir or ".", "remote", "get-url", remote],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, stdin=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _match_push(tokens: list[str], cwd: str) -> ActionMatch | None:
    if tokens[:1] == ["gh"] and tokens[1:3] == ["repo", "create"] and "--public" in tokens:
        return ActionMatch("git_push_to_public_repo", "gh repo create --public: " + " ".join(tokens))
    if tokens[:1] != ["git"]:
        return None
    # Skip git's global options: -C <path>, -c <k=v>, --no-pager, --git-dir=...
    i, repo_dir = 1, cwd
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] in ("-C", "-c") and i + 1 < len(tokens):
            if tokens[i] == "-C":
                repo_dir = str(Path(cwd or ".") / tokens[i + 1])
            i += 2
        else:
            i += 1
    if i >= len(tokens) or tokens[i] != "push":
        return None
    args = _positionals(tokens[i + 1:])
    remote = args[0] if args else "origin"
    if _looks_local(remote):
        return None
    url = remote if "://" in remote or "@" in remote else _git_remote_url(repo_dir, remote)
    if url and _looks_local(url):
        return None
    where = f"{remote} ({url})" if url and url != remote else remote
    return ActionMatch("git_push_to_public_repo", f"git push to {where}: " + " ".join(tokens))


# ── add_dependency ──────────────────────────────────────────────────────────

_MANIFESTS = re.compile(
    r"^(requirements[\w.-]*\.txt|package\.json|pipfile|cargo\.toml|go\.mod|gemfile|"
    r"environment\.ya?ml|build\.gradle(\.kts)?|pom\.xml|composer\.json)$",
    re.IGNORECASE,
)
# (command prefix, subcommand) pairs that add a package when followed by a package name.
_INSTALLERS = [
    (["pip"], "install"), (["pip3"], "install"), (["python", "-m", "pip"], "install"),
    (["python3", "-m", "pip"], "install"), (["py", "-m", "pip"], "install"),
    (["uv", "pip"], "install"), (["uv"], "add"), (["poetry"], "add"), (["pipenv"], "install"),
    (["npm"], "install"), (["npm"], "i"), (["npm"], "add"), (["yarn"], "add"), (["pnpm"], "add"),
    (["cargo"], "add"), (["go"], "get"), (["gem"], "install"), (["conda"], "install"),
    (["dotnet", "add"], "package"),
]
# Flags whose presence means "install what is already declared", not "add something new".
_RESTORE_FLAGS = {"-e", "--editable", "-r", "--requirement"}


def _match_install(tokens: list[str]) -> ActionMatch | None:
    for prefix, sub in _INSTALLERS:
        n = len(prefix)
        if tokens[:n] != prefix or tokens[n:n + 1] != [sub]:
            continue
        rest = tokens[n + 1:]
        if any(t in _RESTORE_FLAGS or t.startswith(("-e", "-r")) and len(t) > 2 for t in rest):
            return None
        packages = [t for t in _positionals(rest) if t != "."]
        if packages:
            return ActionMatch("add_dependency", "install: " + " ".join(tokens))
        return None
    return None


def _edited_text(tool_input: dict) -> str:
    parts = [tool_input.get("content", ""), tool_input.get("new_string", "")]
    parts += [e.get("new_string", "") for e in tool_input.get("edits", []) or []]
    return "\n".join(p for p in parts if p)


def _match_manifest(path: str, tool_input: dict) -> ActionMatch | None:
    name = PurePosixPath(path.replace("\\", "/")).name
    if _MANIFESTS.match(name):
        return ActionMatch("add_dependency", f"write dependency manifest {path}")
    if name.lower() == "pyproject.toml" and re.search(r"dependencies|requires", _edited_text(tool_input)):
        return ActionMatch("add_dependency", f"edit dependencies in {path}")
    return None


# ── modify_schema ───────────────────────────────────────────────────────────

_SCHEMA_SUFFIXES = {".sql", ".prisma", ".graphql", ".gql"}
_SCHEMA_DIRS = {"migrations", "alembic", "migrate"}
_DDL = re.compile(r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|VIEW|SCHEMA|DATABASE|COLUMN)\b", re.IGNORECASE)
_MIGRATION_COMMANDS = [
    re.compile(p) for p in (
        r"\balembic\s+(upgrade|downgrade|revision|stamp)\b",
        r"\bmanage\.py\s+(migrate|makemigrations)\b",
        r"\bprisma\s+(migrate|db\s+push)\b",
        r"\b(rails|rake)\s+db:",
        r"\b(knex|sequelize|typeorm)\b.*\bmigrat",
        r"\bflyway\s+migrate\b",
    )
]


def _match_schema_file(path: str) -> ActionMatch | None:
    p = PurePosixPath(path.replace("\\", "/"))
    if (p.suffix.lower() in _SCHEMA_SUFFIXES or p.name.lower().startswith("schema.")
            or _SCHEMA_DIRS & {part.lower() for part in p.parts[:-1]}):
        return ActionMatch("modify_schema", f"write schema/migration file {path}")
    return None


def _match_schema_command(command: str) -> ActionMatch | None:
    if _DDL.search(command) or any(rx.search(command) for rx in _MIGRATION_COMMANDS):
        return ActionMatch("modify_schema", "schema change: " + command.strip()[:300])
    return None


# ── public API ──────────────────────────────────────────────────────────────

def match_action(tool_name: str, tool_input: dict, cwd: str = "") -> ActionMatch | None:
    """Return the registered action pattern this pending tool call matches, if any."""
    tool_input = tool_input or {}

    if tool_name in _SHELL_TOOLS:
        command = tool_input.get("command", "") or ""
        segments = _segments(command)
        for tokens in segments:
            if m := _match_push(tokens, cwd):
                return m
        if m := _match_schema_command(command):
            return m
        for tokens in segments:
            if m := _match_install(tokens):
                return m
        return None

    if tool_name in _WRITE_TOOLS:
        path = tool_input.get("file_path", "") or ""
        return _match_schema_file(path) or _match_manifest(path, tool_input)

    if tool_name == "TodoWrite":
        todos = tool_input.get("todos") or []
        if todos and all(t.get("status") == "completed" for t in todos):
            return ActionMatch("claim_done", f"marking all {len(todos)} todos completed")

    return None


def is_director_call(tool_name: str, tool_input: dict) -> bool:
    """Is this shell call the director command (config.DIRECTOR_COMMAND), in any
    segment of the line (e.g. after a `cd … &&`)?"""
    if tool_name not in _SHELL_TOOLS:
        return False
    from synthetic_user.config import DIRECTOR_COMMAND
    head = DIRECTOR_COMMAND.split()
    return any(tokens[:len(head)] == head for tokens in _segments((tool_input or {}).get("command", "") or ""))


def hook_output_for(match: ActionMatch, verdict: dict) -> dict | None:
    """Map a brain verdict to PreToolUse output (§2.9).

    proceed → allow (no output) · redirect → allow + injected context ·
    halt → deny with reason · anything else (director unavailable, unreadable
    verdict) → deny: the registered patterns fail CLOSED (FM-19).
    """
    kind = verdict.get("verdict")
    reason = verdict.get("reason") or ""
    if kind == "proceed":
        return None
    if kind == "redirect":
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": f"director redirect on {match.pattern}",
            "additionalContext": f"SYNTHETIC-USER DIRECTOR ({match.pattern}): {reason}",
        }}
    if kind == "halt":
        why = f"Synthetic-user director halted this {match.pattern} action: {reason}"
    else:
        why = (f"Synthetic-user director unavailable for a registered action ({match.pattern}); "
               f"failing closed. {reason}").strip()
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": why,
    }}
