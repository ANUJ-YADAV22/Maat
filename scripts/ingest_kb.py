"""Build the REAL knowledge base from documents you supply (never from model memory).

Two steps, with a human in the loop:

  extract  Scan .txt/.md/.pdf files for sentences that state a numeric requirement and write
           candidates (unverified, with the verbatim quote, document, section and page).
  promote  After a reviewer edits the candidates file (fills subject/attribute, sets
           "approved": true), write approved entries to data/clause_kb/real/ as verified by the
           named reviewer. Unapproved candidates are never loaded by the gate.

Usage:
  python scripts/ingest_kb.py extract docs/*.pdf --domain site_safety --out candidates.json
  python scripts/ingest_kb.py promote candidates.json --verifier "A. Reviewer" --name osha
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from maat.kb import KBEntry

NUM = r"(\d+(?:\.\d+)?)"
UNITS = r"(mm|cm|m|km|kn|n|kpa|mpa|kg|t|deg|degrees|inches|inch|in|ft|feet|lbs|lb|psf|%|days|hours)"
REQ_RE = re.compile(
    rf"\b(?:not less than|at least|minimum of|minimum|not more than|at most|maximum of|maximum|"
    rf"shall be|must be|within)\b[^.;]{{0,60}}?{NUM}\s*{UNITS}\b",
    re.I,
)
SECTION_RE = re.compile(
    r"^\s*(?:section|clause|§)?\s*(\d+(?:\.\d+){0,4}(?:\([a-z0-9]+\))*)[\s.:)-]", re.I
)


def read_pages(path: Path) -> list[tuple[int | None, str]]:
    """Return (page_number, text) pairs; plain text files are a single page-less chunk."""
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("PDF input needs pypdf: pip install pypdf") from exc
        return [(i, p.extract_text() or "") for i, p in enumerate(PdfReader(str(path)).pages, 1)]
    return [(None, path.read_text(errors="replace"))]


def extract_candidates(
    pages: list[tuple[int | None, str]], source_doc: str, domain: str
) -> list[dict[str, Any]]:
    """Find sentences stating a numeric requirement, remembering the nearest section number."""
    out: list[dict[str, Any]] = []
    for page, text in pages:
        section = "?"
        for line in text.splitlines():
            if m := SECTION_RE.match(line):
                section = m.group(1)
            for sentence in re.split(r"(?<=[.;])\s+", line):
                m = REQ_RE.search(sentence)
                if m:
                    out.append(
                        {
                            "id": f"cand_{len(out) + 1:04d}",
                            "subject": "",
                            "attribute": "",
                            "value": float(m.group(1)),
                            "unit": m.group(2).lower(),
                            "domain": domain,
                            "source_doc": source_doc,
                            "section": section,
                            "page": page,
                            "quote": sentence.strip(),
                            "approved": False,
                        }
                    )
    return out


def promote(
    candidates: list[dict[str, Any]], verifier: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate approved candidates and return (kb rows, problems). Nothing is guessed."""
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    for c in candidates:
        if not c.get("approved"):
            continue
        row = {k: v for k, v in c.items() if k != "approved"}
        row.update(verified=True, verified_by=verifier)
        try:
            entry = KBEntry(**row)
        except ValueError as exc:
            problems.append(f"{c.get('id')}: {exc}")
            continue
        if not entry.subject.strip() or not entry.attribute.strip() or entry.section == "?":
            problems.append(f"{c.get('id')}: subject, attribute and section must be filled in")
            continue
        rows.append(entry.model_dump())
    return rows, problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("files", nargs="+", type=Path)
    ex.add_argument(
        "--domain", required=True, choices=["structural_codes", "site_safety", "tender_docs"]
    )
    ex.add_argument("--out", type=Path, default=Path("candidates.json"))
    pr = sub.add_parser("promote")
    pr.add_argument("candidates", type=Path)
    pr.add_argument("--verifier", required=True)
    pr.add_argument("--name", required=True)
    pr.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    args = ap.parse_args()
    if args.cmd == "extract":
        allc: list[dict[str, Any]] = []
        for f in args.files:
            allc += extract_candidates(read_pages(f), f.name, args.domain)
        for i, c in enumerate(allc, 1):
            c["id"] = f"cand_{i:04d}"
        args.out.write_text(json.dumps(allc, indent=2, ensure_ascii=False) + "\n")
        print(
            f"wrote {len(allc)} unverified candidates to {args.out}; review and set approved=true"
        )
        return
    rows, problems = promote(json.loads(args.candidates.read_text()), args.verifier)
    for p in problems:
        print("PROBLEM:", p)
    if problems:
        raise SystemExit("fix the problems above; nothing was written")
    dest = args.data_dir / "clause_kb" / "real" / f"{args.name}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} verified entries to {dest}")


if __name__ == "__main__":
    main()
