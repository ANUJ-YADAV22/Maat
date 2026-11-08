"""Number formatting shared by the agent, the mock backend and the data builders."""

from __future__ import annotations


def fmt_num(x: float | int | str) -> str:
    """Render numbers without float noise (45.0 -> '45', 1.60 -> '1.6'); strings pass through."""
    if isinstance(x, str):
        return x
    x = round(float(x), 6)
    if x.is_integer():
        return str(int(x))
    return f"{x:.6f}".rstrip("0").rstrip(".")
