"""PreToolUse action-pattern matching (architecture2.md §2.9, TBD-2c).

The four registered patterns are the irreversible-by-definition floor: they gate
the pending tool call through the brain regardless of whether the framework
chose to consult. This pins WHICH calls match — the part that must be
deterministic. The brain's verdict on a match is live-LLM and is exercised by
scenario 16.

FAST TEST — no LLM calls (the git-remote cases use a real throwaway repo).
"""
import subprocess

import pytest

from hooks.action_patterns import match_action, hook_output_for


def _bash(command: str) -> tuple[str, dict]:
    return "Bash", {"command": command}


def _pattern(tool_name: str, tool_input: dict, cwd: str = "") -> str | None:
    m = match_action(tool_name, tool_input, cwd)
    return m.pattern if m else None


# ── add_dependency ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("command", [
    "pip install requests",
    "pip3 install requests==2.32.0",
    "python -m pip install -U httpx",
    "uv add httpx",
    "uv pip install rich",
    "poetry add pydantic",
    "npm install lodash",
    "npm i -D jest",
    "yarn add react",
    "pnpm add zod",
    "cargo add serde",
    "go get github.com/pkg/errors",
    "gem install rails",
    "conda install numpy",
    "dotnet add package Newtonsoft.Json",
    "cd app && pip install flask",
])
def test_installing_a_package_is_add_dependency(command):
    assert _pattern(*_bash(command)) == "add_dependency"


@pytest.mark.parametrize("command", [
    "pip install -e .",
    "pip install -e '.[dev]'",
    "pip install -r requirements.txt",
    "npm install",
    "npm ci",
    "pip list",
    "python -m pytest",
    "uv sync",
])
def test_restoring_or_listing_is_not_add_dependency(command):
    assert _pattern(*_bash(command)) is None


@pytest.mark.parametrize("path", [
    "requirements.txt", "requirements-dev.txt", "app/package.json", "Pipfile",
    "Cargo.toml", "go.mod", "Gemfile", "environment.yml",
])
def test_writing_a_manifest_is_add_dependency(path):
    assert _pattern("Write", {"file_path": path, "content": "x"}) == "add_dependency"


def test_pyproject_counts_only_when_dependencies_are_touched():
    dep_edit = {"file_path": "pyproject.toml", "old_string": "dependencies = []",
                "new_string": 'dependencies = ["requests"]'}
    other_edit = {"file_path": "pyproject.toml", "old_string": 'addopts = "-q"',
                  "new_string": 'addopts = "-v"'}
    assert _pattern("Edit", dep_edit) == "add_dependency"
    assert _pattern("Edit", other_edit) is None


# ── modify_schema ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "db/init.sql", "prisma/schema.prisma", "api/schema.graphql", "db/schema.rb",
    "app/migrations/0002_add_email.py", "alembic/versions/abc123_add.py",
])
def test_writing_schema_files_is_modify_schema(path):
    assert _pattern("Write", {"file_path": path, "content": "x"}) == "modify_schema"


@pytest.mark.parametrize("command", [
    "alembic upgrade head",
    "python manage.py migrate",
    "python manage.py makemigrations",
    "npx prisma migrate dev",
    "prisma db push",
    "rails db:migrate",
    "sqlite3 app.db 'CREATE TABLE users(id INTEGER)'",
    'psql -c "ALTER TABLE users ADD COLUMN email text"',
])
def test_running_migrations_or_ddl_is_modify_schema(command):
    assert _pattern(*_bash(command)) == "modify_schema"


@pytest.mark.parametrize("command", [
    "sqlite3 app.db 'SELECT * FROM users'",
    "cat models.py",
])
def test_reads_are_not_modify_schema(command):
    assert _pattern(*_bash(command)) is None


def test_ordinary_source_edit_matches_nothing():
    assert _pattern("Write", {"file_path": "src/app.py", "content": "print(1)"}) is None
    assert _pattern("Read", {"file_path": "db/init.sql"}) is None


# ── claim_done ──────────────────────────────────────────────────────────────

def _todos(*statuses):
    return {"todos": [{"content": f"t{i}", "status": s, "activeForm": "x"} for i, s in enumerate(statuses)]}


def test_marking_every_todo_complete_is_claim_done():
    assert _pattern("TodoWrite", _todos("completed", "completed")) == "claim_done"


def test_partial_progress_is_not_claim_done():
    assert _pattern("TodoWrite", _todos("completed", "in_progress")) is None
    assert _pattern("TodoWrite", {"todos": []}) is None


# ── git_push_to_public_repo ─────────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "work"
    bare = tmp_path / "mirror.git"
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "origin",
                    "https://github.com/example/project.git"], check=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "mirror", str(bare)], check=True)
    return str(work)


@pytest.mark.parametrize("command", [
    "git push",
    "git push origin main",
    "git push --force origin main",
    "git -C . push origin HEAD",
    "git add -A && git commit -m wip && git push",
    "gh repo create demo --public --source .",
])
def test_pushing_to_a_network_remote_matches(repo, command):
    m = match_action("Bash", {"command": command}, repo)
    assert m is not None and m.pattern == "git_push_to_public_repo"


@pytest.mark.parametrize("command", [
    "git push mirror main",           # remote name resolving to a local path
    "git push ../mirror.git main",    # a path given directly
    "git push file:///tmp/x.git",
    "git stash push -m wip",          # not a push at all
    "git status",
])
def test_local_pushes_and_non_pushes_do_not_match(repo, command):
    assert match_action("Bash", {"command": command}, repo) is None


def test_powershell_commands_are_matched_too():
    assert _pattern("PowerShell", {"command": "pip install requests"}) == "add_dependency"


# ── verdict → PreToolUse output (§2.9 mapping) ──────────────────────────────

def _decision(out):
    return out["hookSpecificOutput"].get("permissionDecision") if out else None


def test_proceed_allows_silently():
    m = match_action(*_bash("pip install requests"))
    assert hook_output_for(m, {"verdict": "proceed", "reason": "requested"}) is None


def test_redirect_allows_with_injected_context():
    m = match_action(*_bash("pip install requests"))
    out = hook_output_for(m, {"verdict": "redirect", "reason": "pin the version in requirements.txt"})
    assert _decision(out) == "allow"
    assert "pin the version" in out["hookSpecificOutput"]["additionalContext"]


def test_halt_denies_with_reason():
    m = match_action(*_bash("pip install requests"))
    out = hook_output_for(m, {"verdict": "halt", "reason": "not needed; stdlib urllib suffices"})
    assert _decision(out) == "deny"
    assert "stdlib" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_unavailable_director_fails_closed():
    # FM-19: on the registered action patterns the safe direction is DENY.
    m = match_action(*_bash("pip install requests"))
    out = hook_output_for(m, {"verdict": "unavailable", "reason": "brain error"})
    assert _decision(out) == "deny"
