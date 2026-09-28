"""Local web UI: setup checks, start a Run, watch it live, browse past Runs.

Standard library only (http.server) — nothing extra to install. Binds to
127.0.0.1 and only answers requests whose Host is localhost, so it is not
reachable from the network and a malicious web page cannot drive it
(POSTs must be JSON, which a cross-site form cannot send).
"""
from __future__ import annotations

import json
import re
import threading
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from synthetic_user import config, doctor, runner

_INDEX = Path(__file__).resolve().parent / "index.html"
_ICON = Path(__file__).resolve().parent / "icon.png"
_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
_APP_ID = "synthetic-user"
DEFAULT_PORT = 8765

# Setup checks are cached so the page loads instantly; "Re-check" refreshes them.
_checks_cache: list[dict] | None = None
_checks_lock = threading.Lock()


def _checks(refresh: bool = False, live: bool = False) -> list[dict]:
    global _checks_cache
    with _checks_lock:
        if refresh or live or _checks_cache is None:
            _checks_cache = [c.to_dict() for c in doctor.run_checks(live=live)]
        return _checks_cache


def _model_info() -> dict:
    return {
        "tiers": config.MODELS,
        "defaults": config.MODEL_TIERS,
        "resolved": {role: config.model_for(role) for role in config.MODEL_TIERS},
    }


def _with_liveness(row: dict) -> dict:
    # A "running" record whose Run is not in this process was cut off (UI closed mid-run).
    if row.get("status") == "running" and row.get("id") != runner.active_run_id():
        row = {**row, "status": "interrupted"}
    return row


class _Handler(BaseHTTPRequestHandler):
    server_version = "synthetic-user-ui"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    # ── plumbing ────────────────────────────────────────────────────────────
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in _ALLOWED_HOSTS

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(status, json.dumps(data, default=str).encode("utf-8"), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def _body(self) -> dict:
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("expected application/json")
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    # ── routes ──────────────────────────────────────────────────────────────
    def do_GET(self):
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "local access only")
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send(200, _INDEX.read_bytes(), "text/html; charset=utf-8")
        if path in ("/icon.png", "/favicon.ico"):
            return self._send(200, _ICON.read_bytes(), "image/png")
        if path == "/api/ping":
            return self._json({"app": _APP_ID})
        if path == "/api/status":
            return self._json({"checks": _checks(), "active_run": runner.active_run_id(),
                               "models": _model_info()})
        if path == "/api/runs":
            return self._json([_with_liveness(r) for r in runner.list_runs()])
        m = re.fullmatch(r"/api/runs/([0-9a-f]{32})", path)
        if m:
            record = runner.load_run(m.group(1))
            return self._json(_with_liveness(record)) if record else self._error(404, "no such run")
        return self._error(404, "not found")

    def do_POST(self):
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "local access only")
        try:
            body = self._body()
        except ValueError as exc:
            return self._error(400, str(exc))
        path = self.path.split("?", 1)[0]
        if path == "/api/shutdown":
            self._json({"stopping": True, "active_run": runner.active_run_id()})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return None
        if path == "/api/checks":
            return self._json({"checks": _checks(refresh=True, live=bool(body.get("live")))})
        if path == "/api/runs":
            try:
                session = runner.start_run(
                    str(body.get("goal", "")),
                    models={k: str(v) for k, v in (body.get("models") or {}).items()},
                    use_workspace=bool(body.get("use_workspace", True)),
                    allow_tests=bool(body.get("allow_tests", False)),
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            except RuntimeError as exc:
                return self._error(409, str(exc))
            return self._json({"id": session.id}, 201)
        return self._error(404, "not found")


def _running_instance(port: int) -> bool:
    """True if a Synthetic User UI is already answering on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            return json.loads(r.read()).get("app") == _APP_ID
    except Exception:  # noqa: BLE001
        return False


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Start the UI and open it — or, if it is already running, just open it.

    Clicking the launcher twice therefore never fails: the second click finds the
    running backend and only opens a browser tab. If something else holds the
    port, the next free one is used.
    """
    for candidate in range(port, port + 10):
        if _running_instance(candidate):
            url = f"http://localhost:{candidate}/"
            print(f"Synthetic User is already running at {url}")
            if open_browser:
                webbrowser.open(url)
            return
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", candidate), _Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"No free port between {port} and {port + 9}.")

    url = f"http://localhost:{candidate}/"
    print(f"Synthetic User is running at {url}")
    print("Use the Quit button on the page (or Ctrl+C here) to stop it.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
