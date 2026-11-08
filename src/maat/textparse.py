"""Deterministic parsers for the templated task inputs (shared by runtime and mock backend)."""

from __future__ import annotations

import re

QA_RE = re.compile(r"what is the ([\w\-]+) of ([\w:\-\.]+?)\?", re.I)
COMPUTE_RE = re.compile(r"compute:\s*([0-9eE\.\+\-\*/%\(\)\s]+)", re.I)
CONVERT_RE = re.compile(r"convert:\s*([0-9\.]+)\s*([a-z0-9]+)\s*->\s*([a-z0-9]+)", re.I)
KV_RE = re.compile(r"(\w+)=([^;]+)")


def parse_qa(text: str) -> tuple[str, str] | None:
    """Return (attribute, subject) from 'What is the <attr> of <subject>?' or None."""
    m = QA_RE.search(text)
    return (m.group(1).lower(), m.group(2).lower()) if m else None


def parse_compute(text: str) -> str | None:
    """Return the arithmetic expression of a 'COMPUTE: ...' task, or None."""
    m = COMPUTE_RE.search(text)
    return m.group(1).strip() if m else None


def parse_convert(text: str) -> tuple[float, str, str] | None:
    """Return (value, src_unit, dst_unit) of a 'CONVERT: 2.5 m -> mm' task, or None."""
    m = CONVERT_RE.search(text)
    return (float(m.group(1)), m.group(2).lower(), m.group(3).lower()) if m else None


def parse_kv(text: str) -> dict[str, str]:
    """Return key=value pairs separated by ';' found in the text."""
    return {k.lower(): v.strip() for k, v in KV_RE.findall(text)}
