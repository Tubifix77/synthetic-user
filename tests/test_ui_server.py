"""Web UI server: routes answer, and it refuses anything that isn't local JSON.

FAST TEST — no LLM calls and no Runs started (the status route runs the cheap,
non-live setup checks only).
"""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from synthetic_user.ui import server


@pytest.fixture(scope="module")
def port():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server._Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _req(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    hdrs = {"Host": f"localhost:{port}", **(headers or {})}
    conn.request(method, path, body=body, headers=hdrs)
    r = conn.getresponse()
    return r.status, r.read()


def test_index_page_is_served(port):
    status, body = _req(port, "GET", "/")
    assert status == 200 and b"<title>Synthetic User</title>" in body


def test_status_reports_checks_and_models(port):
    status, body = _req(port, "GET", "/api/status")
    data = json.loads(body)
    assert status == 200
    assert {c["key"] for c in data["checks"]} >= {"python", "claude_cli", "wiring"}
    assert data["models"]["resolved"]["executor"].startswith("claude-")


def test_run_list_is_json(port):
    status, body = _req(port, "GET", "/api/runs")
    assert status == 200 and isinstance(json.loads(body), list)


def test_foreign_host_header_is_refused(port):
    # DNS-rebinding guard: a page on evil.example resolving to 127.0.0.1 is refused.
    status, _ = _req(port, "GET", "/api/status", headers={"Host": "evil.example"})
    assert status == 403


def test_non_json_post_is_refused(port):
    # A cross-site HTML form can only send form encodings, never application/json.
    status, _ = _req(port, "POST", "/api/runs", body="goal=x",
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert status == 400


def test_empty_goal_is_rejected_without_starting_a_run(port):
    status, body = _req(port, "POST", "/api/runs", body=json.dumps({"goal": "  "}),
                        headers={"Content-Type": "application/json"})
    assert status == 400 and "Describe" in json.loads(body)["error"]


def test_unknown_run_id_is_404(port):
    status, _ = _req(port, "GET", "/api/runs/" + "0" * 32)
    assert status == 404


def test_ping_identifies_a_running_instance(port):
    # The launcher uses this to reuse a running backend instead of failing on the port.
    assert server._running_instance(port)
    assert not server._running_instance(1)  # nothing listens on port 1


def test_quit_stops_the_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server._Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    status, body = _req(httpd.server_address[1], "POST", "/api/shutdown", body="{}",
                        headers={"Content-Type": "application/json"})
    assert status == 200 and json.loads(body)["stopping"]
    t.join(timeout=10)
    assert not t.is_alive(), "server kept running after Quit"
    httpd.server_close()
