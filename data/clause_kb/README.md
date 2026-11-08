# Clause knowledge base

`MAAT_KB_MODE=synthetic` (default, used by unit tests) loads `synthetic/*.json`: made-up DEMO-CODE values.
`MAAT_KB_MODE=real` loads `real/*.json`: facts extracted from real documents. Use this for the video demo.

## Entry format (list of objects per file)
`id, subject, attribute, value, unit, domain, source_doc, section, page, quote, verified, verified_by`

- `domain` is one of `structural_codes`, `site_safety`, `tender_docs`.
- `quote` holds the verbatim supporting text so every fact can be audited against its source.
- Only entries with `verified: true` and a named `verified_by` act as authoritative in Lock 2.
  Unverified entries are invisible to the gate, so a claim about them is quarantined, not trusted.
- Maat never invents real values. Every real entry comes from a document you supply.
