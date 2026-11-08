"""Ground-truth unit conversion factors (lowercase unit symbols)."""

from __future__ import annotations

CONVERSIONS: dict[tuple[str, str], float] = {
    ("m", "mm"): 1000.0,
    ("mm", "m"): 0.001,
    ("km", "m"): 1000.0,
    ("m", "km"): 0.001,
    ("kn", "n"): 1000.0,
    ("n", "kn"): 0.001,
    ("mpa", "kpa"): 1000.0,
    ("m2", "cm2"): 10000.0,
    ("kg", "g"): 1000.0,
    ("t", "kg"): 1000.0,
}


def convert(value: float, src: str, dst: str) -> float | None:
    """Convert ``value`` from ``src`` to ``dst``; None if the pair is unknown."""
    factor = CONVERSIONS.get((src.lower(), dst.lower()))
    return None if factor is None else value * factor
