import importlib.util
import json
from pathlib import Path

import pytest

from maat.kb import load_kb

SPEC = importlib.util.spec_from_file_location(
    "ingest_kb", Path(__file__).resolve().parents[2] / "scripts" / "ingest_kb.py"
)
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)

TEXT = """3.1 Guardrails
The top rail shall be not less than 1000 mm above the walking surface.
3.2 Ladders
Ladders must be set at an angle of at most 75 degrees.
General remarks without any number.
"""


def test_extract_finds_requirements_with_quote_and_section() -> None:
    cands = ingest.extract_candidates([(None, TEXT)], "doc.txt", "site_safety")
    assert [(c["value"], c["unit"], c["section"]) for c in cands] == [
        (1000.0, "mm", "3.1"),
        (75.0, "degrees", "3.2"),
    ]
    assert "top rail" in cands[0]["quote"] and cands[0]["approved"] is False


def test_unapproved_or_incomplete_candidates_never_promoted(tmp_path) -> None:
    cands = ingest.extract_candidates([(None, TEXT)], "doc.txt", "site_safety")
    assert ingest.promote(cands, "rev")[0] == []  # nothing approved
    cands[0].update(approved=True)  # approved but subject/attribute missing
    rows, problems = ingest.promote(cands, "rev")
    assert rows == [] and problems
    cands[0].update(subject="scaffold:guardrail", attribute="min_height_mm")
    rows, problems = ingest.promote(cands, "A. Reviewer")
    assert problems == [] and rows[0]["verified_by"] == "A. Reviewer"
    out = tmp_path / "clause_kb" / "real"
    out.mkdir(parents=True)
    (out / "doc.json").write_text(json.dumps(rows))
    kb = load_kb(tmp_path, "real")
    assert kb.check_claim("scaffold:guardrail", "min_height_mm", 1000) == "match"
    assert kb.check_claim("scaffold:guardrail", "min_height_mm", 900) == "contradiction"


def test_pdf_reading_with_pages(tmp_path) -> None:
    pytest.importorskip("pypdf")
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    pdf = tmp_path / "code.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 750, "1.2 Cover")
    c.drawString(72, 730, "Cover shall be not less than 40 mm for severe exposure.")
    c.showPage()
    c.drawString(72, 750, "2.4 Spacing")
    c.drawString(72, 730, "Spacing must be at most 300 mm.")
    c.save()
    cands = ingest.extract_candidates(ingest.read_pages(pdf), "code.pdf", "structural_codes")
    assert [(x["page"], x["section"], x["value"]) for x in cands] == [
        (1, "1.2", 40.0),
        (2, "2.4", 300.0),
    ]
