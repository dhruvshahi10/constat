# Onboarding samples

Raw client documents in the formats a real client actually sends — PDF, DOCX, plain text —
used to demonstrate the onboarding path end to end. All content is fictional.

Reproduce the `northwind` workspace from scratch:

```bash
rm -rf data/evidence/northwind
python onboard.py new-tenant --tenant northwind --name "Northwind Health"
python onboard.py stage --tenant northwind --from data/onboarding_samples/northwind
python onboard.py review --tenant northwind
python onboard.py promote --tenant northwind --id POL-ACCESS-CONTROL \
    --actor "Priya Nair <priya.nair@northwind.example>"
```

Two things to watch in the review queue:

- `ISO 27001 Certification Roadmap` types as **roadmap**, not certificate, and is flagged
  `POSSIBLE CERTIFICATE/ATTESTATION`. Ingestion will not hand over the one field that
  satisfies the certification gate — a human sets it deliberately or not at all.
- `Data Retention and Deletion Standard` mentions "certificate of deletion" in its body and
  still types as **standard**. Filename evidence beats body prose.

Nothing staged is citable. Every staged source is `approval_status: draft`, which the
citation gate refuses, until a named human promotes it.
