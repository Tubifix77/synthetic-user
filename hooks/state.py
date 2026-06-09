"""Per-Run state files for hook handlers (architecture2.md section 2.9).

The executor sets SYNTH_SESSION_DIR before spawning CC. Hook handlers use it to
locate their shared state. If the env var is absent (manual CC run), everything
degrades gracefully to no-ops.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path


def session_dir() -> Path | None:
    """Return the per-session state directory, or None if not set."""
    d = os.environ.get("SYNTH_SESSION_DIR")
    return Path(d) if d else None


def log_hook_event(event: dict) -> None:
    """Append a hook event record to the session's hooks_log.jsonl."""
    d = session_dir()
    if d is None:
        return
    d.mkdir(parents=True, exist_ok=True)
    entry = {**event, "ts": time.time()}
    with open(d / "hooks_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_hooks_log(state_dir: Path) -> list[dict]:
    """Read all hook event records from a session state directory."""
    log_path = state_dir / "hooks_log.jsonl"
    if not log_path.exists():
        return []
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def filter_hook_events(
    events: list[dict],
    *,
    hook: str | None = None,
    action: str | None = None,
) -> list[dict]:
    """Return events matching all supplied filters (None = no constraint on that field)."""
    result = events
    if hook is not None:
        result = [e for e in result if e.get("hook") == hook]
    if action is not None:
        result = [e for e in result if e.get("action") == action]
    return result


def get_counted_tokens() -> int:
    """Return accumulated token estimate for this session."""
    d = session_dir()
    if d is None:
        return 0
    path = d / "token_counter.json"
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text()).get("counted_tokens", 0))
    except Exception:
        return 0


def add_counted_tokens(delta: int) -> int:
    """Add delta to the counter; return the new total."""
    d = session_dir()
    if d is None:
        return 0
    d.mkdir(parents=True, exist_ok=True)
    path = d / "token_counter.json"
    total = get_counted_tokens() + delta
    path.write_text(json.dumps({"counted_tokens": total}))
    return total


def get_dispatch_lock() -> bool:
    """True if consult_director already fired this turn (prevents Stop-hook double-fire)."""
    d = session_dir()
    if d is None:
        return False
    lock_path = d / "dispatch_lock.json"
    if not lock_path.exists():
        return False
    try:
        return bool(json.loads(lock_path.read_text())["locked"])
    except Exception:
        return False


def set_dispatch_lock(locked: bool) -> None:
    d = session_dir()
    if d is None:
        return
    d.mkdir(parents=True, exist_ok=True)
    (d / "dispatch_lock.json").write_text(json.dumps({"locked": locked}))


def clear_dispatch_lock() -> None:
    set_dispatch_lock(False)


def get_interrupt_flag() -> bool:
    d = session_dir()
    if d is None:
        return False
    flag_path = d / "interrupt_flag.json"
    if not flag_path.exists():
        return False
    try:
        return json.loads(flag_path.read_text())["active"]
    except Exception:
        return False


def set_interrupt_flag(active: bool) -> None:
    d = session_dir()
    if d is None:
        return
    d.mkdir(parents=True, exist_ok=True)
    (d / "interrupt_flag.json").write_text(json.dumps({"active": active}))
