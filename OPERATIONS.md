# Synthetic User — Operations Manual

How to install, sign in, run and troubleshoot Synthetic User on your own machine.

This is the hands-on companion to [README.md](README.md) (what the system is) and [architecture2.md](architecture2.md) (why it is shaped this way). Section 12 of architecture2.md is the honest account of what the running system actually does.

---

## 0. Quick start

You need two things installed first: **Python 3.11 or newer** ([python.org](https://www.python.org/downloads/); on Windows tick *"Add python.exe to PATH"*) and **Claude Code** ([claude.com/claude-code](https://claude.com/claude-code)). You also need a Claude account on a Pro, Max, Team or Enterprise plan.

1. **Sign in to Claude Code once.** Open a terminal, run `claude`, type `/login`, and finish the sign-in in your browser.
2. **Get the project.** Download or clone `https://github.com/Tubifix77/synthetic-user`.
3. **Start it.**
   - **Windows:** double-click `start.bat` in the project folder, once. It installs everything and puts a **Synthetic User** icon on your desktop. From then on, **double-click that icon**: it starts the backend (no window stays open) and opens the app in your default browser. Clicking it while the app is already running just opens it again.
   - **Mac / Linux / any terminal:** from the project folder, run `python -m pip install -e ".[dev]"` once, then `python -m synthetic_user`.

The app opens at `http://localhost:8765`. The **Setup** panel on the left runs every check and shows a fix for anything that is missing. When it says **Ready**, type what you want built, then click **Start run** and watch it work.

To stop the app, click **Quit** at the top right of the page. If the icon is ever missing, `python -m synthetic_user shortcut` puts it back. When the app runs without a window, its messages go to `run_state/ui.log`.

---

## 1. What you are running

Synthetic User is a control wrapper around **Claude Code**. It does not replace Claude Code. It drives the official `claude` command-line tool headlessly (`claude -p`) and plays the human-operator roles around it automatically: triage, steering, watching the context, guarding risky actions, and evaluation.

So the core requirement is simple: **a working, signed-in `claude` CLI that can run non-interactively.** Almost every setup problem is really an authentication or permission problem at that layer. Sections 3 and 9 deal with those.

---

## 2. Prerequisites

1. **Python 3.11 or newer.** Check with `python --version`. The project was built and verified on 3.14.
2. **Git**, to clone the repo. The Run page also uses it to list the files a Run changed.
3. **The Claude Code CLI**, runnable as `claude`. If `claude --version` prints a version, you have it.

You also need **an account with a Claude Code-eligible plan**: Pro, Max, Team, an enterprise seat, or an API key. A free account cannot connect Claude Code, and the login tells you so.

---

## 3. Sign in the CLI for headless use

Claude Code inside its desktop app can be signed in while the *command-line* `claude` is not, because they hold credentials separately. Synthetic User uses the command line.

**3.1 Check.** Run `claude auth status`. If it shows `"loggedIn": true`, you are done. The Setup panel and `python -m synthetic_user doctor` run the same check.

**3.2 Sign in.** In a normal terminal, run `claude` and then `/login` at its prompt. Finish the browser flow; if no browser opens, copy the URL the terminal prints. If you get *"Claude Max or Pro is required"*, that account has no entitlement: sign in with the right one, or set `ANTHROPIC_API_KEY`.

**3.3 Verify headless operation.** In a plain terminal, run `claude -p "reply with OK" --output-format json` and look for `"is_error": false`. **Test a live call** in the Setup panel does the same thing on the cheapest model.

**3.4 Trust the folder (recommended).** Run `claude` interactively once *inside the project folder* and accept the trust dialog. Until you do, the CLI prints *"Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has not been trusted"*. Runs still work, because the executor grants what it needs on the command line (§7), but trusting the folder keeps the CLI's view and yours the same. Trust is keyed by the exact path spelling, so trust from the desktop app may not count.

---

## 4. Install

> **One-command setup:** `python bootstrap.py` checks prerequisites, installs the package, verifies sign-in, smoke-tests headless execution and runs the fast tests. It stops with an actionable message at the first failure. `start.bat` also installs automatically on first launch.

```
git clone https://github.com/Tubifix77/synthetic-user.git
cd synthetic-user
python -m pip install -e ".[dev]"
```

This installs the project in editable mode plus `pytest`. The runtime itself needs only the standard library and the `claude` CLI.

The repo is location-independent: every hook path resolves relative to the repo root, so nothing needs configuring after you clone or move it.

The install also creates a `synth` command. On Windows it usually lands in a per-user Scripts folder that isn't on `PATH`, so this manual uses `python -m synthetic_user`, which always works. `synth …` is the same command if it is on your `PATH`.

---

## 5. Verify the install

**5.1 Setup check.** Run `python -m synthetic_user doctor`, or add `--live` to include one tiny real call.

**5.2 Fast tests (no LLM calls, seconds).** These cover the pure-Python logic: scenarios 1, 2, 9 and 15, the halt-language corpus, the action-pattern matcher, hook gating, model routing, permissions and subprocess hygiene.

```
python -m pytest -m "not integration"
```

If these fail, the problem is the install or the Python environment, not Claude Code.

**5.3 Integration tests (live `claude -p`, minutes each, uses plan quota).**

```
python -m pytest -m integration
python -m pytest tests/test_scenario_16.py -v      # a single scenario
```

A clean full run (`python -m pytest`) is all seventeen scenarios passing, plus the fast unit tests. The live scenarios run Claude Code in the repo root, and a test Run can create or edit project files, so check `git status` afterwards and discard anything a Run wrote. Some scenarios run for several minutes (the triple-check and multi-hat panel make several model calls in series). Don't wrap them in a runner with a short timeout.

---

## 6. Run your own goal

A Run is one bounded goal-pursuit. Triage decides whether to accept it, Claude Code executes it, the evaluator scores each cycle, and the seeder decides when it is done.

**From the web page** (`python -m synthetic_user` or `start.bat`): type a goal and click **Start run**. The page shows a live timeline of what happened. That covers triage, each cycle, the tools Claude used, questions it put to the director, guardrail decisions and context-steward interventions. It then shows what Claude reported, the files it created, and a decision log with every component's reasoning. **Past runs** keeps them all.

**From the terminal:**

```
python -m synthetic_user run "Write a Python script that reverses a file line by line, with tests" --allow-tests
python -m synthetic_user runs
```

Options that apply to both:

- **Workspace folder (on by default).** Each Run is told to put its files in `workspace/<date>-<goal>/`, which is gitignored, so Run output doesn't mix with the project's own files. Untick it (or pass `--here`) to work in the repo root.
- **Let Claude run its tests (off by default).** This allows `pytest` and nothing else. Running tests executes code Claude just wrote, unattended, so it is a per-Run opt-in. See §7, *Permissions*.
- **Models.** Sonnet 5 and Haiku 4.5 by default. Change any role per Run in the page's **Models** section, or with `--model executor=haiku` on the command line.

**From Python** (for scripting or experiments):

```python
from synthetic_user.orchestrator import Orchestrator
from synthetic_user.executor import ClaudeCodeExecutor
from synthetic_user.memory import Memory
from synthetic_user.types import Request

memory = Memory()
executor = ClaudeCodeExecutor()                     # drives `claude -p` in this repo
run = Orchestrator(memory=memory, executor_fn=executor.execute).run(
    Request(goal="write a Python script that reverses a file line-by-line"))

print(run.stop_code, len(run.cycles))
print(run.deliverable.content if run.deliverable else "(none)")
for r in memory.all_reports():
    print(f"  [{r.component}] {r.decision_type}: {r.rationale[:80]}")
```

`Orchestrator` without `executor_fn` uses the instant stub executor, which is what the fast scenarios use. `synthetic_user.runner` is the layer the page and CLI use; it adds the workspace, the per-Run settings and the `run_state/<id>/run.json` record.

What to expect:

- **Triage** may turn down a goal with no software deliverable (try "write me something interesting").
- **Steering is automatic.** If Claude stops to ask, the `Stop` hook gets it an answer; if it calls `consult_director`, the brain answers inline. You don't intervene.
- **Guardrails are automatic.** Pushing to a remote, adding a dependency, changing a schema or claiming "done" is put to the director before it happens (§8).

---

## 7. Configuration and tuning

Everything lives in `synthetic_user/config.py`.

**Models.** `MODELS` maps the tiers to concrete IDs (`haiku` → `claude-haiku-4-5-20251001`, `sonnet` → `claude-sonnet-5`, `opus` → `claude-opus-5-5`). `MODEL_TIERS` assigns a tier to each role:

| Role | Default | What it does |
|---|---|---|
| `executor` | sonnet | Claude Code doing the actual work |
| `triage` | haiku | screens the request |
| `director` | sonnet | answers the framework's questions, judges guardrails |
| `director_hard_call` | haiku | the triple-check passes (fast: Claude is blocked meanwhile) |
| `hat_correctness`, `hat_user_intent` | sonnet | evaluator panel |
| `hat_adversary` | haiku | evaluator panel, on a different tier on purpose |
| `escape_audit` | haiku | post-hoc check for decisions made without asking |

Every `claude -p` call resolves its model through `model_for(role)`. That is the only place models are chosen (a fast test enforces it). To override one role without editing code, set `SYNTH_MODEL_<ROLE>`, e.g. `SYNTH_MODEL_HAT_ADVERSARY=opus`, or to a full model ID. Re-routing the Adversary hat to another model family is exactly this override (architecture2.md §12.5).

**Permissions.** The executor runs `claude -p --dangerously-skip-permissions`. Organisation policy can **disable bypass mode**, and then that flag silently degrades to `acceptEdits`: file edits still go through, but every other tool call is denied, because nobody is there to approve it. So the executor also passes explicit allow rules (`--allowedTools`):

- `EXECUTOR_ALLOWED_TOOLS` is always granted: the director command (`python -m synthetic_user.director`), plus read-only `ls`, `git status`, `git diff` and `git log`.
- `TEST_RUN_TOOLS` is granted only with `SYNTH_ALLOW_TESTS=1` (the page's checkbox, or `--allow-tests`): `pytest`.
- `SYNTH_EXTRA_ALLOWED_TOOLS` takes more rules, separated by semicolons, e.g. `Bash(npm test:*);Bash(make check)`.

Grant the narrowest rule that does the job. A blanket `Bash` rule would recreate the bypass mode your policy turned off.

**Other tunables:** `SCORE_THRESHOLD` (0.70, the evaluator's Layer-1 pass bar) and `MAX_CYCLES_PER_RUN` (25, a safety bound; the real stop signal is the seeder).

**Test-time knobs** (force rare paths deterministically; not for normal use):

- `SYNTH_DIRECTOR_DISABLED=1`: the director command answers "Director unavailable" without asking the brain. It is the authoritative off switch for the proactive path (scenario 3).
- `SYNTH_REACTIVE_TEST=1`: skip the SessionStart instruction so the framework halts instead of consulting (scenarios 3 and 13).
- `SYNTH_COMPACT_THRESHOLD_TOKENS`: lower the steward's trigger (scenarios 5 and 11).
- `SYNTH_EVAL_ANOMALY_THRESHOLD`: force the Layer-2 panel to fire (scenarios 8 and 12).
- `SYNTH_EVAL_LAYER2_DISABLED=1`: simulate the panel faulting out (scenario 12).
- `SYNTH_IN_TRIPLE_CHECK`: an internal lock the brain sets on itself; don't set it by hand.

**Hooks only act inside a Run.** `.claude/settings.json` registers the hooks for *every* Claude Code session opened in this folder, including your own. They only do anything when `SYNTH_SESSION_DIR` is set, which only the executor sets, so opening Claude Code here yourself is safe: no "no human at the keyboard" instruction, and no director answering your questions for you.

If you change `.claude/settings.json`, fully restart any `claude` session so it re-reads it.

**No MCP servers.** Company policy allows only official MCP servers, so this project registers none: there is deliberately no `.mcp.json`, and `doctor` warns if one appears.

---

## 8. How steering and guardrails work

**Proactive path (the normal one).** The `SessionStart` hook tells Claude that, when it would ask the user a question, it should run `python -m synthetic_user.director "question" "context"` through its Bash tool instead. The command blocks while the brain answers, prints the answer, and Claude continues in the same turn without halting. If the brain can't answer, the command prints an explicit "Director unavailable" and Claude carries on with its best judgement, stating its assumption. (This used to be an MCP tool; company policy now allows only official MCP servers.)

The time budget is nested so a director call is never cut off mid-answer. The brain works to a 300-second deadline, after which it answers "unavailable". The `PreToolUse` hook sets every director call's tool timeout to 480 seconds, whatever Claude asked for. The executor makes sure the CLI's per-command maximum (600 seconds) isn't lowered, and switches off auto-backgrounding, which would otherwise return "moved to background" instead of an answer. The values live in `config.py` (`DIRECTOR_DEADLINE_S`, `DIRECTOR_TOOL_TIMEOUT_MS`).

**Reactive path (safety net).** If Claude writes a question or an approval request instead of consulting, the `Stop` hook's router recognises the halt-language, the brain answers, and the answer is injected so the same session continues. A fast test pins the router against a corpus of halts and look-alike completion sentences.

**Guardrails (action patterns).** Before every tool call, the `PreToolUse` hook checks for four registered, irreversible-by-definition actions:

| Pattern | Matches |
|---|---|
| `git_push_to_public_repo` | `git push` to a network remote, `gh repo create --public` (pushes to local paths are not matched) |
| `add_dependency` | `pip/uv/poetry/npm/yarn/pnpm/cargo/go/gem/conda/dotnet add/install <package>`, writing `requirements*.txt`, `package.json`, `Cargo.toml`, etc., dependency edits in `pyproject.toml` |
| `modify_schema` | writing `*.sql`/`*.prisma`/`*.graphql`, `schema.*` or files under `migrations/`/`alembic/`, running migrations, DDL (`CREATE/ALTER/DROP TABLE…`) |
| `claim_done` | a TodoWrite marking every item completed |

On a match, the director gives a verdict. **Proceed** lets the action run. **Redirect** lets it run with guidance injected. **Halt** blocks it and tells Claude why. If the director can't be reached or its answer can't be read, the action is **blocked** (fail closed). Ordinary tool calls never involve the director.

---

## 9. Troubleshooting

**The Setup panel says "Signed in to Claude ✕", or `claude -p` says "Not logged in".** The command-line CLI has no credentials. Redo §3.2 in a plain terminal.

**"Claude Max or Pro is required".** The account has no Claude Code entitlement. Use an account on an eligible plan, or set `ANTHROPIC_API_KEY`.

**A Run says it "needs approval" to run tests or commands.** Bypass mode is disabled on this machine (§7, *Permissions*), and the command isn't on the allow list. Tick **Let Claude run its tests** for pytest, or add a narrow rule with `SYNTH_EXTRA_ALLOWED_TOOLS`. The executor tells Claude that denied tools can't be approved, so it carries on and reports what it couldn't verify.

**"Ignoring 1 permissions.allow entry … this workspace has not been trusted".** Harmless for Runs, which grant what they need on the command line. To silence it, run `claude` once in the project folder and accept the trust dialog (§3.4).

**The director keeps answering "Director unavailable".** Its answer says why. "Switched off for this Run" means `SYNTH_DIRECTOR_DISABLED=1` is set. "No synthetic-user Run is active" means it was run outside a Run. "The brain could not answer" is followed by the brain's error. "Deadline reached" means the 300-second budget ran out.

**Internal calls hang until a timeout.** Every internal `claude -p` must get `stdin=subprocess.DEVNULL`: the CLI waits on any inherited pipe. A fast test (`tests/test_subprocess_hygiene.py`) enforces this; if you add a new subprocess call, give it an explicit `stdin`.

**Garbled characters (`â€”` instead of `—`) in answers.** Something decoded Claude's UTF-8 as the Windows default code page. All subprocess calls pass `encoding="utf-8"`, and the hooks read stdin as UTF-8; keep it that way in new code.

**`synth` is "not recognized".** The Scripts folder isn't on `PATH`. Use `python -m synthetic_user …` instead; it is the same command.

**Setup shows "a .mcp.json is present".** Delete it. This project must not register an MCP server (company policy), and a project `.mcp.json` also brings back Claude Code's "Pending approval" prompt.

**An integration test "hangs" then fails.** Usually it is just slow: the triple-check and multi-hat scenarios run several model calls in series. Run it alone to watch it.

**The steward never seems to fire.** `PostToolUse` only runs for tools that actually execute; a denied tool never reaches it.

**Fast tests fail.** Reinstall with `python -m pip install -e ".[dev]"` and confirm Python is 3.11+.

---

## 10. What this manual does not cover

- **The design rationale:** why there are exactly these roles, the failure modes, and the multi-hat evaluator. See [architecture2.md](architecture2.md).
- **Upgrading the v1 stand-ins:** SQLite + vector memory, LLM-reflective brain escalation, LLM-backed seeder reflection and a real Layer-1 evaluator. These are planned swaps behind stable interfaces (architecture2.md §12.4).
- **Anthropic's products beyond "install and sign in the CLI".** Check Anthropic's own documentation; it changes faster than this file.
