# GOTCHAS.md (append-only)

- 2026-08-08 — bash_tool runs /bin/sh: brace expansion silently creates a literal `{a,b}` directory. Use explicit mkdir paths.
- 2026-08-08 — openpyxl writes formulas with no cached value; recalc via LibreOffice before anything reads data_only. Delivered XLSX must be recalced too.
- 2026-08-08 — Merged cells: only the anchor cell is writable; export must never touch row 1.
- 2026-08-08 — Second-order quarantine: contradicted retention policy correctly killed the *deletion-certificate* answer too (PRV-01.1). Feature, not bug — documented in README.
- 2026-08-08 — constat-v0.zip shipped `make_questionnaire.py` with the web-chat sandbox's absolute output path (`/home/claude/…`), which crashes anywhere else. Output path now derives from `__file__`.
- 2026-08-08 — Google 404s dated Gemini models for NEW accounts ("no longer available to new users") even though ListModels still lists them. Default is now the rolling `gemini-flash-latest` alias. Also: Gemini 3.x thinks by default and can blow a 60s read timeout — `thinkingLevel: low` + 120s timeout fixed it (the gates do the verification, not the model).
