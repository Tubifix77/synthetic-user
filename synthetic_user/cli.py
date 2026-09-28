"""`synth` — the command-line front end.

    synth              open the web UI (same as `synth ui`)
    synth doctor       check the setup; --live also makes one tiny real call
    synth run "goal"   run a goal in the terminal and follow it live
    synth runs         list past runs
    synth shortcut     put a one-click icon on the Windows desktop

Also available as `python -m synthetic_user ...` when the Scripts folder is not
on PATH.
"""
from __future__ import annotations

import argparse
import sys
import time

from synthetic_user.executor import PROJECT_ROOT

# The hooks package lives beside synthetic_user and is imported by path.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_PATTERNS = {
    "git_push_to_public_repo": "push to a remote",
    "claim_done": "claim done",
    "add_dependency": "add a dependency",
    "modify_schema": "change a schema",
}


def _line(event: dict) -> str | None:
    """One terminal line per interesting event (mirrors the web UI's timeline)."""
    kind, hook, action = event.get("kind"), event.get("hook"), event.get("action")
    if kind == "triage":
        return "triage: accepted" if event.get("route") == "loop" else f"triage: rejected — {event.get('reason')}"
    if kind == "cycle_start":
        return "cycle 1: Claude is working…" if event["index"] == 0 else \
            f"cycle {event['index'] + 1}: refining — {event.get('goal', '')[:100]}"
    if kind == "cycle_end":
        return f"cycle {event['index'] + 1}: {'pass' if event.get('passed') else 'fail'} (score {event.get('score'):.2f})"
    if hook == "PreToolUse" and action == "allow":
        return f"  · {event.get('tool')}"
    if hook == "PreToolUse" and action == "action_pattern":
        return (f"  ! guardrail ({_PATTERNS.get(event.get('pattern'), event.get('pattern'))}): "
                f"director said {event.get('verdict')} → {event.get('decision')}. {event.get('reason', '')}")
    if hook == "consult_director":
        return f"  ? asked the director: {event.get('question_preview', '')[:120]}"
    if hook == "Stop" and action == "halt_intercepted":
        return "  ? Claude stopped to ask; the director answered"
    if hook == "PostToolUse" and action == "suggest_compact":
        return "  ~ steward: asked Claude to summarise its context"
    return None


def cmd_doctor(args) -> int:
    from synthetic_user.doctor import run_checks
    checks = run_checks(live=args.live)
    for c in checks:
        mark = "OK" if c.ok else ("!!" if c.blocking else " !")
        print(f"[{mark}] {c.label}: {c.detail}")
        if not c.ok and c.fix:
            print(f"     fix: {c.fix}")
    ok = all(c.ok or not c.blocking for c in checks)
    print("\nReady." if ok else "\nFix the items marked [!!] and run `synth doctor` again.")
    return 0 if ok else 1


def cmd_run(args) -> int:
    from synthetic_user import runner
    models = dict(m.split("=", 1) for m in args.model or [])
    session = runner.start_run(args.goal, models=models, use_workspace=not args.here,
                               allow_tests=args.allow_tests)
    print(f"Run {session.id}" + (f" — files go to {session.record['workspace']}/" if session.workspace else ""))
    seen = 0
    while True:
        done = not session._thread.is_alive()
        record = runner.load_run(session.id) or session.record
        events = sorted(record.get("progress", []) + record.get("hook_events", []), key=lambda e: e["ts"])
        for event in events[seen:]:
            text = _line(event)
            if text:
                print(text, flush=True)
        seen = len(events)
        if done:
            break
        time.sleep(1.0)
    record = runner.load_run(session.id) or session.record
    print()
    if record["status"] == "complete":
        last = record["cycles"][-1] if record["cycles"] else {}
        if record.get("stop_code") == "circular":
            print("Stopped without passing: the evaluator failed the work and one retry didn't fix it.")
        print(("Done.\n\n" if record.get("stop_code") != "circular" else "\n")
              + (last.get("deliverable") or "").strip())
        if record["files_changed"]:
            print("\nFiles created or changed:\n  " + "\n  ".join(record["files_changed"]))
        return 0
    print(f"Run {record['status']}: {record.get('error') or ''}")
    return 1


def cmd_runs(args) -> int:
    from synthetic_user import runner
    rows = runner.list_runs()
    if not rows:
        print("No runs yet. Start one with `synth run \"...\"` or `synth ui`.")
    for r in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["started_at"] or 0))
        print(f"{when}  {r['status']:<11} {r['goal'][:70]}")
    return 0


def cmd_ui(args) -> int:
    from synthetic_user.ui.server import serve
    serve(port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_shortcut(args) -> int:
    """Put a "Synthetic User" icon on the Windows desktop: one double-click starts
    the backend (no console window) and opens the UI in the default browser."""
    if sys.platform != "win32":
        print("Desktop shortcuts are Windows-only. Elsewhere, run: python -m synthetic_user")
        return 1
    import subprocess
    from pathlib import Path
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    target = pythonw if pythonw.exists() else Path(sys.executable)
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Synthetic User.lnk'));"
        f"$s.TargetPath='{target}';"
        "$s.Arguments='-m synthetic_user ui';"
        f"$s.WorkingDirectory='{PROJECT_ROOT}';"
        f"$s.IconLocation='{Path(__file__).resolve().parent / 'ui' / 'icon.ico'},0';"
        "$s.Description='Open Synthetic User in your browser';"
        "$s.Save();"
        "Join-Path $d 'Synthetic User.lnk'"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        print(f"Could not create the shortcut: {r.stderr.strip()}")
        return 1
    print(f"Created {r.stdout.strip()} — double-click it to open Synthetic User.")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Model output is full of non-ASCII (→, —, …); a Windows console or pipe
    # defaults to cp1252 and would crash printing it.
    if sys.stdout is None:
        # Started windowless (pythonw, e.g. from the desktop shortcut): keep a log
        # so a failure is findable instead of vanishing.
        log_dir = PROJECT_ROOT / "run_state"
        log_dir.mkdir(exist_ok=True)
        sys.stdout = sys.stderr = open(log_dir / "ui.log", "a", encoding="utf-8", buffering=1)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser =argparse.ArgumentParser(prog="synth", description="Synthetic User — Claude Code with a stand-in operator.")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("ui", help="open the web UI (default)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    p.set_defaults(fn=cmd_ui)

    p = sub.add_parser("doctor", help="check that everything is set up")
    p.add_argument("--live", action="store_true", help="also make one tiny real call (uses a little quota)")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("run", help="run a goal and follow it in the terminal")
    p.add_argument("goal")
    p.add_argument("--model", action="append", metavar="ROLE=TIER",
                   help="override a role's model, e.g. --model executor=haiku (repeatable)")
    p.add_argument("--here", action="store_true", help="work in the repo root instead of a workspace/ folder")
    p.add_argument("--allow-tests", action="store_true",
                   help="let Claude run pytest (this executes the code it wrote)")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("runs", help="list past runs")
    p.set_defaults(fn=cmd_runs)

    p = sub.add_parser("shortcut", help="put a one-click 'Synthetic User' icon on the Windows desktop")
    p.set_defaults(fn=cmd_shortcut)

    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        args = parser.parse_args(["ui", *(argv or [])])
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
