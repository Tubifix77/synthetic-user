"""
bootstrap.py — one-command setup for synthetic-user.

Run from the repo root:
    python bootstrap.py

Walks from a fresh clone to a verified working install. Stops on the first
hard failure with an actionable message. Does not require anything to be
installed first — stdlib only.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# ── helpers ─────────────────────────────────────────────────────────────────

def step(label: str) -> None:
    print(f"\n[  ] {label}", flush=True)

def ok(label: str) -> None:
    print(f"\r[OK] {label}", flush=True)

def fail(message: str) -> None:
    print(f"\n[!!] {message}", flush=True)
    sys.exit(1)

def warn(message: str) -> None:
    print(f"[??] {message}", flush=True)

def run_cmd(args: list[str], *, capture: bool = True, timeout: int = 120,
            env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=capture,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
        env=env,
    )

# ── checks ───────────────────────────────────────────────────────────────────

def check_python_version() -> None:
    step("Checking Python version (need 3.11+)")
    v = sys.version_info
    if (v.major, v.minor) < (3, 11):
        fail(
            f"Python {v.major}.{v.minor} found — 3.11 or newer is required.\n"
            "    Install a newer Python from python.org and re-run this script\n"
            "    with the right interpreter, e.g.:  python3.11 bootstrap.py"
        )
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def check_git_and_node() -> None:
    step("Checking git and node on PATH")
    for tool, install_hint in [
        ("git", "https://git-scm.com/downloads"),
        ("node", "https://nodejs.org (required by the claude CLI)"),
    ]:
        if shutil.which(tool) is None:
            warn(
                f"'{tool}' not found on PATH. Install it from {install_hint}\n"
                "    then re-run this script. Some steps may still work without it\n"
                "    but the claude CLI requires Node.js at runtime."
            )
        else:
            ok(tool)


def check_claude_cli() -> None:
    step("Checking claude CLI (claude --version)")
    if shutil.which("claude") is None:
        fail(
            "'claude' not found on PATH. Install the Claude Code CLI:\n"
            "    Option A (npm):    npm install -g @anthropic-ai/claude-code\n"
            "    Option B (native): use the installer from claude.ai/download\n"
            "    After installation, open a new terminal and re-run this script."
        )
    try:
        result = run_cmd(["claude", "--version"])
        version = (result.stdout or result.stderr or "").strip().splitlines()[0]
        ok(f"claude CLI — {version}")
    except Exception as exc:
        fail(f"'claude --version' failed: {exc}")


def install_package() -> None:
    step("Installing package in editable mode  (pip install -e '.[dev]')")
    result = run_cmd(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
        capture=True,
    )
    if result.returncode != 0:
        fail(
            "pip install failed. Error output:\n"
            + (result.stderr or result.stdout or "(no output)")
            + "\n    Fix the error above and re-run this script."
        )
    ok("Package installed")


def check_auth() -> None:
    step("Checking claude authentication (claude auth status)")
    try:
        result = run_cmd(["claude", "auth", "status"], timeout=30)
        output = (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        fail("'claude' disappeared from PATH unexpectedly. Re-install the CLI.")
    except subprocess.TimeoutExpired:
        fail("'claude auth status' timed out. Check your network connection.")

    # Parse the output for 'loggedIn: true' (claude prints YAML-ish status).
    logged_in = "loggedIn: true" in output or '"loggedIn": true' in output

    if not logged_in:
        print()
        print("─" * 70)
        print("  NOT LOGGED IN — headless mode will not work until you fix this.")
        print()
        print("  How to log in:")
        print("  1. Open a new terminal (PowerShell on Windows).")
        print("  2. Run:  claude")
        print("  3. At the claude> prompt, run:  /login")
        print("  4. Complete the browser OAuth flow. Use a Pro/Max or")
        print("     enterprise account — a free account cannot connect Claude Code.")
        print("     If the browser doesn't open, copy the URL the terminal prints.")
        print("  5. Once logged in, exit the claude shell and re-run this script:")
        print("       python bootstrap.py")
        print()
        print("  If login shows 'Max or Pro is required', that account lacks the")
        print("  entitlement. Log out and use the right account, or set")
        print("  ANTHROPIC_API_KEY in your environment to bypass OAuth.")
        print("─" * 70)
        sys.exit(1)

    ok("claude is authenticated")


def smoke_test_headless() -> None:
    step("Smoke-testing headless execution  (claude -p 'reply with OK')")
    try:
        result = run_cmd(
            ["claude", "-p", "reply with OK", "--output-format", "json"],
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        fail(
            "claude -p timed out after 60 s.\n"
            "    This usually means an authentication issue. Check 'claude auth status'\n"
            "    and redo the login steps if needed."
        )
    except FileNotFoundError:
        fail("'claude' not found. Re-install the CLI.")

    output = (result.stdout or "").strip()
    if not output:
        fail(
            "claude -p returned no output (exit code %d).\n" % result.returncode
            + "    stderr: " + (result.stderr or "(empty)").strip()
        )

    # Check for auth error before trying to parse JSON.
    if "not logged in" in output.lower() or "please run /login" in output.lower():
        print()
        print("─" * 70)
        print("  claude -p says 'Not logged in' even though auth status passed.")
        print("  This can happen when the CLI and the desktop app hold separate")
        print("  credentials. Redo the login from a plain terminal (not inside the")
        print("  claude interactive shell) — see the instructions printed above.")
        print("─" * 70)
        sys.exit(1)

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        # Non-JSON output is acceptable if there's no error indicator.
        if result.returncode == 0:
            ok("Headless execution works (non-JSON response, exit 0)")
            return
        fail(
            f"claude -p returned non-JSON output (exit {result.returncode}):\n"
            f"    {output[:300]}"
        )
        return

    if data.get("is_error"):
        error_msg = data.get("result") or data.get("error") or str(data)
        if "not logged in" in str(error_msg).lower():
            print()
            print("─" * 70)
            print("  claude -p is not logged in. Complete the browser OAuth flow")
            print("  (see the instructions above) and re-run this script.")
            print("─" * 70)
            sys.exit(1)
        fail(f"claude -p returned an error:\n    {error_msg[:300]}")

    ok("Headless execution works")


def run_fast_tests() -> None:
    step("Running fast test suite (no LLM calls)")
    fast_tests = [
        "tests/test_scenario_01.py",
        "tests/test_scenario_02.py",
        "tests/test_scenario_09.py",
        "tests/test_scenario_15.py",
    ]
    result = run_cmd(
        [sys.executable, "-m", "pytest"] + fast_tests + ["-q"],
        capture=True,
        timeout=300,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        fail(
            "Fast tests failed. Output:\n"
            + output[-1500:]
            + "\n    Fix the failures above before running the full integration suite."
        )
    # Print the pytest summary line(s) so the user can see test counts.
    for line in output.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            print(f"    {line.strip()}")
    ok("Fast tests passed")


def print_success() -> None:
    print()
    print("=" * 70)
    print("  All checks passed. The repo is ready to use.")
    print()
    print("  What passed:")
    print("    • Python 3.11+")
    print("    • git and node on PATH")
    print("    • claude CLI installed and authenticated")
    print("    • Package installed (pip install -e '.[dev]')")
    print("    • Headless claude -p works end-to-end")
    print("    • Fast test suite (4 scenarios)")
    print()
    print("  Next steps:")
    print("    • Run the full integration suite (requires live claude -p, ~minutes):")
    print("        python -m pytest -m integration -v")
    print()
    print("    • Run all 15 scenarios at once:")
    print("        python -m pytest -v")
    print()
    print("    • Drive a real Run — see OPERATIONS.md section 6 for the")
    print("      minimal Python snippet and what to expect.")
    print("=" * 70)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("synthetic-user bootstrap")
    print(f"Repo: {REPO_ROOT}")
    print()

    check_python_version()
    check_git_and_node()
    check_claude_cli()
    install_package()
    check_auth()
    smoke_test_headless()
    run_fast_tests()
    print_success()


if __name__ == "__main__":
    main()
