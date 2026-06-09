# Synthetic User — Operations Manual

How to install, authenticate, verify, and run Synthetic User on your own machine.

This is the hands-on companion to [README.md](README.md) (what the system is) and [architecture2.md](architecture2.md) (why it is shaped this way). You do not need to read those to follow this, but section 12 of architecture2.md is the honest account of what the running system actually does.

---

## 1. What you are running

Synthetic User is a control wrapper around **Claude Code**. It does not replace Claude Code — it drives the official `claude` command-line tool headlessly and sits around it, playing the human-operator roles (triage, steering, context-watching, evaluation) automatically.

So the core requirement is simple: **a working, logged-in `claude` CLI that can run non-interactively.** Almost every setup problem is really an authentication problem at that layer. Section 3 deals with it carefully.

---

## 2. Prerequisites

You need four things on the machine:

1. **Python 3.11 or newer.** Check with `python --version`. The project was built and verified on 3.14.
2. **Git**, to clone the repo.
3. **Node.js**, because the `claude` CLI is distributed through npm. Get it from nodejs.org if you don't have it.
4. **The Claude Code CLI**, installed and runnable as `claude`. If `claude --version` prints a version, you have it. If not, install it per Anthropic's current instructions (the native installer or `npm install -g`), then re-check.

You also need **an Anthropic account with a Claude Code-eligible plan** — a Pro or Max subscription, an enterprise seat, or an API key. A free account cannot connect Claude Code; the login will tell you so. (During this project's build, a personal account without Pro/Max was rejected at login and an enterprise seat worked — if you have both, log in with the one that carries the entitlement.)

---

## 3. Authenticate the CLI for headless use

This is the step that matters most and the one most likely to bite you. Claude Code running *inside* its own desktop app can be logged in while the *command-line* `claude` is not — they hold credentials separately. Synthetic User uses the command line, so the command line must be logged in.

**Step 3.1 — Check current status.**

```
claude auth status
```

If it reports `loggedIn: true`, skip to section 4. If it reports `loggedIn: false` / `authMethod: none`, continue.

**Step 3.2 — Log in.** In a normal terminal (PowerShell on Windows), start the CLI and run the login command inside it:

```
claude
```

then at the prompt:

```
/login
```

This opens a browser OAuth flow. If the browser doesn't open on its own, the terminal prints a URL — copy it into your browser manually. Sign in with the account that has the eligible plan. If the flow shows a code, paste it back into the terminal where prompted.

> If login fails with *"Claude Max or Pro is required to connect to Claude Code"*, the account you used doesn't carry the entitlement. Log out and repeat with the right account, or use an API key instead (set the `ANTHROPIC_API_KEY` environment variable and skip the OAuth flow entirely).

**Step 3.3 — Verify headless operation.** This is the real test — it exercises the exact path the wrapper uses. In a plain terminal (not inside the `claude` interactive shell):

```
claude -p "reply with OK" --output-format json
```

You want a JSON object whose `result` field is `OK` (or close) and `is_error` is `false`. If you instead see `"Not logged in · Please run /login"`, the headless path still has no credentials — repeat 3.2 and make sure you completed the browser flow.

Once `claude -p` returns real output, the hard part is done.

---

## 4. Get the code and install

**Step 4.1 — Clone (or locate) the repo.**

```
git clone https://github.com/Tubifix77/synthetic-user.git
cd synthetic-user
```

If you already have it, just `cd` into it. (The reference machine keeps it at `D:\AI\Synthetic`; see the path caveat in section 7.)

**Step 4.2 — Install the package and test dependencies.**

```
pip install -e ".[dev]"
```

This installs the project in editable mode plus `pytest`. The runtime itself has almost no third-party dependencies — the heavy lifting is done by the `claude` CLI as a subprocess. The one external piece is the MCP SDK used by the director server; if the MCP server fails to start later with an import error, install it explicitly:

```
pip install mcp
```

---

## 5. Verify the install

There are two tiers of test. Run the fast tier first.

**Step 5.1 — Fast tests (no LLM calls, run in seconds).** These cover the pure-Python logic: the walking skeleton, multi-cycle flow, the Decision Report query interface, and the seeder validation gate.

```
python -m pytest tests/test_scenario_01.py tests/test_scenario_02.py tests/test_scenario_09.py tests/test_scenario_15.py -v
```

All four should pass quickly. If these fail, something is wrong with the install or the Python environment, not with Claude Code — fix that before going further.

**Step 5.2 — The integration tests (live `claude -p`, minutes each).** These are marked `integration` and actually drive Claude Code. They are slower (some, like the triple-check, deliberately make several model calls in series) and they cost usage against your plan.

Run the whole integration tier:

```
python -m pytest -m integration -v
```

or run a single scenario while you're getting set up:

```
python -m pytest tests/test_scenario_03.py -v
```

> **Timeouts.** Some integration scenarios run for a few minutes. Run them in a terminal that won't impose its own short timeout. The executor's own subprocess timeout is set generously (ten minutes) precisely because the triple-check path is slow; don't wrap these tests in a runner that kills them earlier.

**Step 5.3 — Everything at once.**

```
python -m pytest -v
```

A clean run is fifteen passing scenarios.

---

## 6. Drive your own Run

Once the tests pass, you can point the system at a goal of your own. A Run is one bounded goal-pursuit: triage decides whether to accept it, the loop executes through Claude Code, the evaluator scores each cycle, and the seeder decides when it's done.

The minimal shape, in Python from the repo root:

```python
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.executor import ClaudeCodeExecutor
from synthetic_user.memory import Memory
from synthetic_user.types import Request

# A fresh memory and a real Claude Code executor for this Run.
memory = Memory()
executor = ClaudeCodeExecutor()          # drives `claude -p` in this repo

orchestrator = Orchestrator(memory=memory, executor_fn=executor.execute)

run = orchestrator.run(Request(goal="write a Python script that reverses a file line-by-line"))

print("stop code:", run.stop_code)
print("cycles:", len(run.cycles))
print("final deliverable:\n", run.deliverable.content if run.deliverable else "(none)")

# Inspect the audit trail — every component's reasoning is here.
for report in memory.all_reports():
    print(f"  [{report.component}] {report.decision_type}: {report.rationale[:80]}")
```

What to expect:

- **Triage** may reject a goal that has no software deliverable (try `goal="write me something interesting"` to see a rejection — `run.stop_code` will be unset and `run.rejected_reason` will explain).
- **The framework will run in this directory.** `ClaudeCodeExecutor` invokes `claude -p` with the repo as its working directory, so any files the task creates land here. (That's why a couple of throwaway scripts from test runs are git-ignored.)
- **Steering happens automatically.** If Claude Code stops to ask a question, the `Stop` hook resolves it and the session continues; if it calls `consult_director`, the brain answers inline. You don't intervene.
- **The audit trail is the point.** `memory.all_reports()` and `memory.query_reports(component=..., decision_type=..., has_flag=...)` let you reconstruct *why* the system did what it did without replaying it.

---

## 7. Configuration and tuning

**Tunable constants** live in `synthetic_user/config.py`:

- `SCORE_THRESHOLD` (default `0.70`) — the evaluator's Layer-1 pass bar.
- `MAX_CYCLES_PER_RUN` (default `25`) — a safety bound; the real stop signal is the seeder, not this.
- `MODEL_TIERS` — which Claude tier each role uses (triage/steward on Haiku, seeder/director on Sonnet, deep evaluator attribution on Opus). This is also where you would re-route the Adversary hat to a different model family if you ever gain access to one (see architecture2.md §12.5).

**Test-time environment knobs** (used to force rare paths deterministically in the test suite; you generally won't set these by hand):

- `SYNTH_REACTIVE_TEST=1` — suppresses the `SessionStart` instruction so the framework does *not* call `consult_director`, forcing the reactive `Stop`-hook path (scenario 3, and any case where you want to test halt-catching).
- `SYNTH_COMPACT_THRESHOLD_TOKENS` — lowers the steward's compaction trigger so scenario 5 fires without a real long context.
- `SYNTH_EVAL_ANOMALY_THRESHOLD` — forces the evaluator's Layer-2 multi-hat panel to fire (scenario 8).
- `SYNTH_IN_TRIPLE_CHECK` — internal dispatch lock the brain sets on itself during a triple-check; not for manual use.

### The path caveat (read this if you cloned to a new location)

The committed `.claude/settings.json` (hook commands) and `.mcp.json` (MCP server command) currently use **absolute paths** pointing at `D:/AI/Synthetic/...`. This is a known rough edge (architecture2.md §12.7). If you cloned the repo somewhere else, the hooks and the `consult_director` server will not be found until you update those paths:

- In **`.claude/settings.json`**, every hook `command` has a hardcoded `python D:/AI/Synthetic/hooks/...` — change the directory to your clone location.
- In **`.mcp.json`**, the server `args` entry points at `D:/AI/Synthetic/director_mcp/consult_director_server.py` — change it the same way.

After editing those two files, fully restart any `claude` session so it re-reads them. The fast tests (section 5.1) don't touch hooks or MCP and will pass regardless; the integration tests (5.2) need the paths correct.

---

## 8. Troubleshooting

**`claude -p` says "Not logged in".** The headless CLI has no credentials. Redo section 3.2 in a plain terminal and make sure you finished the browser OAuth flow. Confirm with `claude auth status`.

**Login rejected: "Max or Pro is required".** The account lacks a Claude Code entitlement. Use an account that has Pro/Max or an enterprise seat, or set `ANTHROPIC_API_KEY` and skip OAuth.

**An integration test "hangs" then fails.** It probably didn't hang — the triple-check and multi-hat scenarios run several model calls in series and take minutes. Make sure nothing is imposing a short timeout around pytest, and that you're not running it through a harness with its own cutoff. Run that one scenario alone to watch it.

**"No MCP servers are connected" / `consult_director` not available.** Two usual causes: the server config is in the wrong file (it must be `.mcp.json`, not `.claude/settings.json`), or the tool isn't permitted (`mcp__synthetic-user__consult_director` must be in `settings.json` → `permissions.allow`). If you relocated the repo, also check the path in `.mcp.json` (section 7). After any change, restart the `claude` session.

**MCP server crashes on start with an import error.** Either the `mcp` SDK isn't installed (`pip install mcp`) or a local directory named `mcp/` is shadowing it — this project uses `director_mcp/` precisely to avoid that; don't rename it back.

**The steward never seems to fire (scenario 5 or in a real Run).** `PostToolUse` only runs for tools that *actually execute*. If Claude Code's permission layer blocks a tool before it runs (for instance, writing outside the project directory), the hook never sees it. Keep task outputs inside the repo.

**Fast tests fail.** This points at the Python install, not Claude Code. Reinstall with `pip install -e ".[dev]"` and confirm your Python is 3.11+.

---

## 9. What this manual does not cover

- **The design rationale** — why there are exactly these roles, what the twenty-one failure modes are, how the multi-hat evaluator resolves "who validates the validator." That's [architecture2.md](architecture2.md).
- **Upgrading the v1 stand-ins** — moving memory to SQLite + vector storage, making brain escalation LLM-reflective rather than keyword-triggered, making the seeder's reflection LLM-backed. These are planned swaps behind stable interfaces (architecture2.md §12.4); they are development work, not operations.
- **Anything about Anthropic's products beyond "install and log in the CLI."** For current Claude Code installation specifics, plan entitlements, and API details, consult Anthropic's own documentation — those change faster than this file.
