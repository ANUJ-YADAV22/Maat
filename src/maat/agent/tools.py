"""Agent tools: clause_lookup over the KB and a safe arithmetic calculator (never eval)."""

from __future__ import annotations

import ast
import operator
from typing import Any

from maat.kb import KnowledgeBase

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def calculator(expr: str) -> float:
    """Evaluate a pure arithmetic expression by walking its AST; anything else is an error."""
    if len(expr) > 200:
        raise ValueError("expression too long")

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 16:
                raise ValueError("exponent too large")
            return _BIN[type(node.op)](left, right)
        raise ValueError(f"unsupported expression element: {type(node).__name__}")

    return ev(ast.parse(expr.strip(), mode="eval"))


def clause_lookup(kb: KnowledgeBase, subject: str, attribute: str) -> dict[str, Any] | None:
    """Deterministic KB lookup of a verified clause value, with its source."""
    entry = kb.lookup(subject, attribute)
    if entry is None:
        return None
    return {
        "value": entry.value,
        "unit": entry.unit,
        "source": f"{entry.source_doc} §{entry.section}",
    }
