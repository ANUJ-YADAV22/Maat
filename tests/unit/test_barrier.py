"""Information barrier: agent/, proposal/ and gate/ must never touch held-out data or the oracle."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "maat"
GUARDED = ("agent", "proposal", "gate")
FORBIDDEN_STRINGS = ("heldout", "held_out_suite", "oracle_label")


def _violations() -> list[str]:
    bad: list[str] = []
    for pkg in GUARDED:
        for path in (SRC / pkg).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                    if node.level:
                        mods = [f"relative:{'.' * node.level}{node.module or ''}"]
                else:
                    mods = []
                for m in mods:
                    parts = m.replace("relative:", "").strip(".").split(".")
                    if "eval" in parts or "oracle" in parts:
                        bad.append(f"{path.relative_to(SRC)} imports {m}")
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if any(s in node.value.lower() for s in FORBIDDEN_STRINGS):
                        bad.append(f"{path.relative_to(SRC)} references {node.value!r}")
    return bad


def test_no_barrier_violations() -> None:
    assert _violations() == []


def test_barrier_detects_a_violation(tmp_path, monkeypatch) -> None:
    """The scanner must actually catch a bad import and a held-out reference."""
    import tests.unit.test_barrier as mod

    pkg = tmp_path / "gate"
    pkg.mkdir()
    (pkg / "bad.py").write_text("from maat.eval import oracle\nX = 'heldout'\n")
    monkeypatch.setattr(mod, "SRC", tmp_path)
    found = mod._violations()
    assert any("imports" in v for v in found) and any("references" in v for v in found)
