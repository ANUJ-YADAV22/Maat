"""Trust domains: which of structural_codes / site_safety / tender_docs a patch belongs to."""

from __future__ import annotations

from maat.kb import KnowledgeBase

SITE_PREFIXES = ("scaffold", "ladder", "excavation", "crane", "incident", "activity")
FAMILY_DOMAIN = {
    "safety_checklist": "site_safety",
    "incident_triage": "site_safety",
    "tender_extract": "tender_docs",
    "clause_query": "structural_codes",
    "unit_calc": "structural_codes",
}


def domain_for(family: str, subject: str | None, kb: KnowledgeBase | None = None) -> str:
    """KB domain of the subject if known, else a prefix rule, else the family default."""
    if subject:
        if kb and (d := kb.subject_domain(subject)):
            return d
        prefix = subject.split(":", 1)[0]
        if prefix in SITE_PREFIXES:
            return "site_safety"
        if prefix == "tender":
            return "tender_docs"
    return FAMILY_DOMAIN.get(family, "structural_codes")
