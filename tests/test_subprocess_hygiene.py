"""Every subprocess the wrapper spawns must set stdin explicitly.

`claude -p` reads piped stdin and waits for EOF. The brain used to run inside
the consult_director MCP server, whose stdin was the JSON-RPC pipe, so an
inherited stdin made every proactive consult hang until the 120 s timeout. The
server is gone (§12.9), but any inherited pipe does the same. This pins the fix
everywhere.

FAST TEST — static check of the source, no processes started.
"""
import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_every_subprocess_run_sets_stdin():
    offenders = []
    for folder in ("synthetic_user", "hooks"):
        for path in (_ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("run", "Popen", "check_output")
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"
                        and not any(k.arg in ("stdin", "input") for k in node.keywords)):
                    offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert not offenders, "subprocess calls inheriting stdin:\n" + "\n".join(offenders)
