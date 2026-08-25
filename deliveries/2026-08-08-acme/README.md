# Acme — security questionnaire response

Engagement date: 2026-08-08

This is the complete output of your Pramana engagement. It is self-contained:
every file below is in this folder, and nothing here needs an internet
connection or an account to open.

**Start with `index.html`.** Open it in any browser. It has the headline
numbers and a link to everything else.

One idea explains the whole package: an answer is released only when an
approved, in-force document supports it, and that document is named next to the
answer. When no such document exists, the engine refuses and says why. A
refusal is the control working — it is the reason the answers you can ship are
worth shipping.

## The files

### `acme_security_questionnaire__DELIVERED.xlsx`
**Your completed questionnaire** — The workbook you were sent, returned with the answers filled in. Row order, question wording and every original tab are unchanged — only the answer columns were written. This is the file you send back.

### `run_report.html`
**Audit working paper** — Every question with its answer, the documents cited underneath it, and the gate decision that released or refused it. This is what you hand an auditor or a buyer who asks how an answer was reached.

### `trust_page/index.html`
**Your trust page** — A publishable page answering the 38 questions buyers ask most often. Only the 13 that are fully evidence-backed are answered; the rest are shown as open items a buyer must request. Host it, or send it as a file. The same answers as data are in trust_page/deflection.json.

### `commitment_register/index.html`
**Commitment register** — The security promises already made in your contracts and RFP responses, checked against the same evidence. 7 of 7 cannot currently be stood behind — contradicted, unsupported, or resting on evidence that expires first. The findings as data are in commitment_register/commitments.json.

### `evidence_gaps.md`
**Your work-list — the evidence gaps** — The 7 questions that could not be answered, grouped by reason, each naming the document to produce, renew or reconcile and who it was routed to. Close these and the same questions answer themselves next time.

### `contracts.json`
**Machine-readable answers** — Every answer as structured data — the citations behind it, its evidence status, and any recorded gap. For loading into your own GRC tooling.

### `audit_log.jsonl`
**Tamper-evident audit log** — One line per step, each carrying the hash of the line before it. Editing any past line breaks the chain from that point on, which is what makes the record checkable rather than merely stored.

### `README.md`
**This package, explained** — A plain-English description of every file here and how to read a refusal.

## The numbers on the cover page

- **17 answered with citations** — answers released with the document, version and location behind them.
- **7 refused** — no approved, in-force document supported an answer, so none was written.
- **7 open items** — the refusals, restated as documents somebody has to produce. This is `evidence_gaps.md`.
- **Audit chain** — verifies intact; unsigned (tamper-evident, not tamper-proof).


## How to read a refusal

A refused question has no answer text. It has a reason, a named document that
has to exist, and a person it was routed to. Refusals are not failures of the
engine; they are the questions where answering from your current evidence would
have meant asserting something you could not support.

Work `evidence_gaps.md` from the top: contradictions first (two approved
documents disagreeing is a live problem regardless of this questionnaire), then
expired documents, then the ones that were never written.

## Questions

Ask your Pramana operator. If something in this package looks wrong, say so
before you send the workbook on — the whole point of the audit log is that the
record can be checked rather than argued about.
