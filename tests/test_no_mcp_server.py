"""The project ships no MCP server (company policy: official MCP servers only).

Guards against the server sneaking back in: no .mcp.json, no server package,
no `mcp` dependency, no MCP tool grants — and `doctor` warns if a .mcp.json
reappears (it would also bring back Claude Code's "Pending approval" prompt).

FAST TEST — no LLM calls.
"""
import json
import tomllib
from pathlib import Path

from synthetic_user import config, doctor

_ROOT = Path(__file__).resolve().parents[1]


def test_no_mcp_config_or_server_package():
    assert not (_ROOT / ".mcp.json").exists()
    assert not (_ROOT / "director_mcp").exists()


def test_no_mcp_dependency():
    deps = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    assert not any(d.split(">")[0].split("=")[0].strip() == "mcp" for d in deps), deps


def test_no_mcp_tool_grants():
    settings = json.loads((_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "mcp__" not in json.dumps(settings)
    assert not any(r.startswith("mcp__") for r in config.EXECUTOR_ALLOWED_TOOLS)


def test_doctor_warns_when_an_mcp_config_appears(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        (_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"), encoding="utf-8")
    clean = doctor.check_wiring(root=tmp_path)
    assert clean.ok

    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"x": {}}}', encoding="utf-8")
    warned = doctor.check_wiring(root=tmp_path)
    assert not warned.ok and not warned.blocking, "a stray .mcp.json is a warning, not a blocker"
    assert ".mcp.json" in warned.detail and "delete" in warned.fix.lower()
