"""Deterministically generate the synthetic KB, task suites and config_v1 (spec section 5).

Every value is made up (DEMO-CODE) so the demo never asserts real engineering numbers. Real-mode
data comes from `scripts/ingest_kb.py` instead. Run: python scripts/build_data.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from maat.fmt import fmt_num
from maat.units import convert

DATA = Path(__file__).resolve().parents[1] / "data"

# (subject, attribute, value, unit, domain)
CLAUSES = [
    ("cover:mild", "min_cover_mm", 31, "mm", "structural_codes"),
    ("cover:moderate", "min_cover_mm", 38, "mm", "structural_codes"),
    ("cover:severe", "min_cover_mm", 47, "mm", "structural_codes"),
    ("cover:extreme", "min_cover_mm", 62, "mm", "structural_codes"),
    ("rebar:spacing", "min_spacing_mm", 73, "mm", "structural_codes"),
    ("slab:thickness", "min_thickness_mm", 118, "mm", "structural_codes"),
    ("column:diameter", "min_dia_mm", 229, "mm", "structural_codes"),
    ("footing:depth", "min_depth_mm", 905, "mm", "structural_codes"),
    ("anchorage:bond", "min_length_mm", 410, "mm", "structural_codes"),
    ("beam:span_depth", "max_ratio", 17, None, "structural_codes"),
    ("scaffold:guardrail", "min_height_mm", 1013, "mm", "site_safety"),
    ("scaffold:toeboard", "min_height_mm", 148, "mm", "site_safety"),
    ("ladder:angle", "max_deg", 74, "deg", "site_safety"),
    ("excavation:shoring", "min_depth_m", 1.6, "m", "site_safety"),
    ("crane:exclusion", "radius_m", 7, "m", "site_safety"),
]
INCIDENTS = [
    ("incident:crane_overload", "major"),
    ("incident:fire_small", "moderate"),
    ("incident:minor_cut", "minor"),
    ("incident:fall_from_height", "critical"),
    ("incident:electric_shock", "critical"),
    ("incident:trench_collapse", "critical"),
]
TENDERS = [
    ("T-101", "2026-12-01", 50000, "Class A contractor"),
    ("T-102", "2027-01-15", 75000, "Class B contractor"),
    ("T-103", "2027-02-28", 120000, "Class AA contractor"),
]
MEMORY_CLAUSES = [
    "cover:mild",
    "cover:moderate",
    "rebar:spacing",
    "slab:thickness",
    "column:diameter",
    "scaffold:guardrail",
    "scaffold:toeboard",
    "ladder:angle",
]
MEMORY_INCIDENTS = ["incident:crane_overload", "incident:fire_small", "incident:minor_cut"]
CHECKLIST_ITEMS = ["harness_inspected", "edge_protection", "ppe_check", "permit_to_work"]


def kb_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, (subj, attr, val, unit, dom) in enumerate(CLAUSES, 1):
        rows.append(_kb(f"kb_{len(rows) + 1:03d}", subj, attr, val, unit, dom, f"{dom[:1]}.{i}"))
    for i, (subj, val) in enumerate(INCIDENTS, 1):
        rows.append(
            _kb(f"kb_{len(rows) + 1:03d}", subj, "severity", val, None, "site_safety", f"i.{i}")
        )
    for tid, dl, emd, elig in TENDERS:
        for attr, val in (("deadline", dl), ("emd_inr", emd), ("eligibility", elig)):
            rows.append(
                _kb(
                    f"kb_{len(rows) + 1:03d}",
                    f"tender:{tid.lower()}",
                    attr,
                    val,
                    None,
                    "tender_docs",
                    f"t.{tid}",
                )
            )
    return rows


def _kb(id_: str, subj: str, attr: str, val: Any, unit: str | None, dom: str, sec: str) -> dict:
    return {
        "id": id_,
        "subject": subj,
        "attribute": attr,
        "value": val,
        "unit": unit,
        "domain": dom,
        "source_doc": "DEMO-CODE-A",
        "section": sec,
        "page": None,
        "quote": None,
        "verified": True,
        "verified_by": "synthetic-seed",
    }


def clause_task(tid: str, subj: str, attr: str, val: Any, suite: str, tags: list[str]) -> dict:
    return {
        "id": tid,
        "family": "clause_query",
        "input": f"What is the {attr} of {subj}?",
        "checker": {"type": "regex", "pattern": rf"\bis {re.escape(fmt_num(val))}\b"},
        "tags": tags,
        "subject_keys": [subj],
        "suite": suite,
    }


def incident_task(tid: str, subj: str, sev: str, ctx: str, suite: str, tags: list[str]) -> dict:
    return {
        "id": tid,
        "family": "incident_triage",
        "input": f"{ctx} What is the severity of {subj}?",
        "checker": {"type": "contains_all", "items": [sev]},
        "tags": tags,
        "subject_keys": [subj],
        "suite": suite,
    }


def unit_task(tid: str, text: str, expected: float, suite: str, tags: list[str]) -> dict:
    return {
        "id": tid,
        "family": "unit_calc",
        "input": text,
        "checker": {"type": "numeric_close", "expected": expected},
        "tags": tags,
        "subject_keys": ["unit:convert" if "CONVERT" in text else "unit:arith"],
        "suite": suite,
    }


def checklist_task(
    tid: str, activity: str, suite: str, tags: list[str], extra: list[str] = ()
) -> dict:
    return {
        "id": tid,
        "family": "safety_checklist",
        "input": f"Prepare the pre-work safety checklist for {activity}.",
        "checker": {"type": "checklist_covers", "items": CHECKLIST_ITEMS + list(extra)},
        "tags": tags,
        "subject_keys": [f"activity:{activity.split()[0]}"],
        "suite": suite,
    }


def tender_task(tid: str, idx: int, phrasing: str, suite: str, tags: list[str]) -> dict:
    t, dl, emd, elig = TENDERS[idx % len(TENDERS)]
    body = f"TENDER {t}: deadline={dl}; emd_inr={emd}; eligibility={elig}"
    return {
        "id": tid,
        "family": "tender_extract",
        "input": f"{phrasing}: {body}",
        "checker": {
            "type": "fields_present",
            "fields": ["deadline", "emd", "eligibility"],
            "values": {"deadline": dl, "emd": str(emd), "eligibility": elig},
        },
        "tags": tags,
        "subject_keys": [f"tender:{t.lower()}"],
        "suite": suite,
    }


def build_golden() -> list[dict]:
    kb = {c[0]: c for c in CLAUSES}
    out = [
        clause_task(f"gold_clause_{i:02d}", s, kb[s][1], kb[s][2], "golden", ["golden"])
        for i, s in enumerate(MEMORY_CLAUSES, 1)
    ]
    sev = dict(INCIDENTS)
    ctxs = [
        "Site report.",
        "Supervisor note.",
        "Daily log.",
        "Audit finding.",
        "Near-miss form.",
        "Shift handover.",
        "Safety walk.",
        "Contractor report.",
    ]
    subs = MEMORY_INCIDENTS * 3
    out += [
        incident_task(
            f"gold_incident_{i:02d}",
            subs[i - 1],
            sev[subs[i - 1]],
            ctxs[i - 1],
            "golden",
            ["golden"],
        )
        for i in range(1, 9)
    ]
    exprs = ["12*4", "7*9", "100/8", "3.5*8+2", "144/12", "25+17", "9*9", "250-33"]
    out += [
        unit_task(
            f"gold_unit_{i:02d}", f"COMPUTE: {e}", round(eval_expr(e), 9), "golden", ["golden"]
        )
        for i, e in enumerate(exprs, 1)
    ]
    acts = [
        "scaffold erection",
        "roof edge repairs",
        "tower crane erection",
        "trench excavation",
        "facade cleaning",
        "steel beam placement",
        "formwork stripping",
        "bridge deck casting",
    ]
    out += [
        checklist_task(f"gold_checklist_{i:02d}", a, "golden", ["golden"])
        for i, a in enumerate(acts, 1)
    ]
    phr = [
        "Extract the tender fields from",
        "Pull out the key fields from",
        "Parse this tender",
        "Read the tender and list fields",
        "Summarise tender fields from",
        "Get deadline, emd and eligibility from",
        "Extract fields",
        "Tender intake",
    ]
    out += [
        tender_task(f"gold_tender_{i:02d}", i, p, "golden", ["golden"])
        for i, p in enumerate(phr, 1)
    ]
    return out


def eval_expr(expr: str) -> float:
    from maat.agent.tools import calculator

    return calculator(expr)


def build_heldout() -> list[dict]:
    kb = {c[0]: c for c in CLAUSES}
    sev = dict(INCIDENTS)
    tags = ["heldout"]
    out = []
    for i, s in enumerate(
        ["cover:severe", "cover:extreme", "anchorage:bond", "slab:thickness", "ladder:angle"], 1
    ):
        out.append(clause_task(f"held_clause_{i:02d}", s, kb[s][1], kb[s][2], "heldout", tags))
    for i, (s, c) in enumerate(
        [
            ("incident:fall_from_height", "Site report."),
            ("incident:electric_shock", "Supervisor note."),
            ("incident:trench_collapse", "Daily log."),
            ("incident:minor_cut", "Audit finding."),
            ("incident:fire_small", "Near-miss form."),
        ],
        1,
    ):
        out.append(incident_task(f"held_incident_{i:02d}", s, sev[s], c, "heldout", tags))
    convs = [(2.5, "m", "mm"), (12, "kn", "n"), (0.75, "km", "m")]
    for i, (v, a, b) in enumerate(convs, 1):
        out.append(
            unit_task(
                f"held_unit_{i:02d}",
                f"CONVERT: {fmt_num(v)} {a} -> {b}",
                round(convert(v, a, b), 9),
                "heldout",
                tags,
            )
        )
    for j, e in enumerate(["6*7", "18+27*2"], len(convs) + 1):
        out.append(
            unit_task(
                f"held_unit_{j:02d}", f"COMPUTE: {e}", round(eval_expr(e), 9), "heldout", tags
            )
        )
    acts = [
        "parapet wall repairs",
        "mast climber assembly",
        "excavator trench work",
        "glazing installation",
    ]
    out.append(
        checklist_task(
            "held_checklist_01", "hot work welding on level 3", "heldout", tags, ["fire_watch"]
        )
    )
    out += [
        checklist_task(f"held_checklist_{i:02d}", a, "heldout", tags) for i, a in enumerate(acts, 2)
    ]
    phr = [
        "Extract",
        "Please extract the fields",
        "Parse tender",
        "List tender fields",
        "Tender record",
    ]
    out += [
        tender_task(f"held_tender_{i:02d}", i + 1, p, "heldout", tags) for i, p in enumerate(phr, 1)
    ]
    return out


def build_invariants() -> list[dict]:
    tags = ["invariant"]
    out = [
        checklist_task(f"inv_{i:02d}", a, "invariants", tags)
        for i, a in enumerate(["scaffold work", "crane lift", "roof work"], 1)
    ]
    out += [
        {
            "id": "inv_04",
            "family": "clause_query",
            "input": "What is the min_cover_mm of cover:mild?",
            "checker": {"type": "tool_called", "tool": "clause_lookup"},
            "tags": tags,
            "subject_keys": ["cover:mild"],
            "suite": "invariants",
        },
        {
            "id": "inv_05",
            "family": "clause_query",
            "input": "What is the max_deg of ladder:angle?",
            "checker": {"type": "tool_called", "tool": "clause_lookup"},
            "tags": tags,
            "subject_keys": ["ladder:angle"],
            "suite": "invariants",
        },
    ]
    for i, idx in enumerate([0, 1], 6):
        t = tender_task(f"inv_{i:02d}", idx, "Extract", "invariants", tags)
        t["checker"] = {"type": "fields_present", "fields": ["deadline", "emd", "eligibility"]}
        out.append(t)
    out.append(
        {
            "id": "inv_08",
            "family": "safety_checklist",
            "input": "Prepare the pre-work safety checklist for roof edge work.",
            "checker": {"type": "checklist_covers", "items": ["harness_inspected"]},
            "tags": tags,
            "subject_keys": ["activity:roof"],
            "suite": "invariants",
        }
    )
    return out


def build_config() -> dict:
    kb = {c[0]: c for c in CLAUSES}
    memory = []
    for s in MEMORY_CLAUSES:
        _, attr, val, _, _ = kb[s]
        memory.append((s, attr, val))
    sev = dict(INCIDENTS)
    memory += [(s, "severity", sev[s]) for s in MEMORY_INCIDENTS]
    return {
        "version": 1,
        "memory": [
            {
                "id": f"m_{i:03d}",
                "subject": s,
                "attribute": a,
                "value": v,
                "text": f"{s} {a} is {fmt_num(v)}",
                "source_patch": None,
                "protected": False,
            }
            for i, (s, a, v) in enumerate(memory, 1)
        ],
        "rules": [
            {
                "id": "r_001",
                "text": "Always call clause_lookup for clause questions.",
                "applies_to": ["clause_query"],
                "protected": True,
            },
            {
                "id": "r_002",
                "text": "All four checklist items are mandatory on every checklist.",
                "applies_to": ["safety_checklist"],
                "protected": True,
            },
            {"id": "r_003", "text": "Answer concisely.", "applies_to": [], "protected": False},
        ],
        "tool_policy": {
            "clause_query": {
                "require": ["clause_lookup"],
                "ground": [],
                "order": ["clause_lookup", "calculator"],
            },
            "unit_calc": {"require": ["calculator"], "ground": [], "order": ["calculator"]},
        },
        "workflow": {
            "clause_query": ["retrieve", "lookup_clause", "final"],
            "incident_triage": ["retrieve", "final"],
            "safety_checklist": [
                "ask_harness_inspected",
                "ask_edge_protection",
                "ask_ppe",
                "ask_permit",
            ],
            "unit_calc": ["compute", "final"],
            "tender_extract": ["extract_deadline", "extract_emd", "extract_eligibility"],
        },
    }


def main() -> None:
    (DATA / "clause_kb" / "synthetic").mkdir(parents=True, exist_ok=True)
    outputs = {
        DATA / "clause_kb" / "synthetic" / "kb.json": kb_rows(),
        DATA / "suites" / "golden.json": build_golden(),
        DATA / "suites" / "heldout.json": build_heldout(),
        DATA / "suites" / "invariants.json": build_invariants(),
        DATA / "config_v1.json": build_config(),
    }
    for path, obj in outputs.items():
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {path.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main()
