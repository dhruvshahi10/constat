# Road to completion

State on 6 Nov 2026, branch `claude/fervent-zhukovsky-b6ef25`, measured rather than remembered. "Complete" means the plan's eight verification steps and its release gates pass, with the knowledge layer able to answer from governed context through every questionnaire channel. Everything marked done was run on that branch; every number is reproducible with the command beside it.

## The definition of done, item by item

| # | Verification step (from the plan) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `pytest` green, golden set 0 dangerous failures | Done | 429 Python tests; golden dev 41 of 41, holdout 0 dangerous (`python evals/run_golden.py --split all`) |
| 2 | Injection suite 100% quarantined or refused | Done | 44 of 44, 4 of them laid out as PDF lines (`python evals/run_injection.py`) |
| 3 | Local end to end: upload, states, approve, edit, route, send, metrics, sent-answer record | Done | `scripts/smoke.py` 12 of 12 over real HTTP; SSE in `tests/test_api_questionnaires.py::test_sse_events_reach_done`; web verified against the live API |
| 4 | Simulator loads the embed; wrong-origin messages ignored; CSP allows Atlan on `/embed` only | Done | Playwright smoke (`npm run test:e2e` in `web/`) and the handshake unit tests |
| 5 | Hosted demo on Vercel, Render and Supabase; p95 under 8 s per question on Haiku; `/healthz` green | **Open: needs Dhruv** | Deploy, then `python scripts/smoke.py --base <render url> --token <token>` |
| 6 | MCP: `answer_question` returns a verdict; a write returns a proposal id | Done in tests; live inspector session open | `tests/test_mcp.py`; an inspector session against a running server is a five-minute manual check |
| 7 | Runbook dry run on a clean machine by someone else, under 60 minutes | **Open: needs a second person** | `docs/runbooks/fde-install.md`; step 9 is now the automated smoke test |
| 8 | Model-evaluation record for `claude-haiku-4-5-20251001` with `claim-contract-v1` | **Open: needs an Anthropic key** | `ANTHROPIC_API_KEY=... python evals/run_live.py`, commit `evals/records/*.json` |

Release gates in CI (`.github/workflows/ci.yml`): pytest, gate branch coverage at or above 95% (now 99%), golden dev split, holdout reported, injection suite, claim-drafting set, eval-record check, and a web job (lint with the copy gate, typecheck, unit tests, Playwright). The web job is new; it had never been wired.

## The knowledge layer, channel by channel

| Channel | Status |
| --- | --- |
| Excel (xlsx) and CSV | Done; answers written back in place for xlsx, a csv of answers otherwise |
| DOCX | Done; export is a new file |
| PDF | Done; numbered items, ids and question-shaped lines, page-scoped ids, a pre-extraction size guard |
| OneTrust, Archer, ProcessUnity | Through their xlsx or csv export, which the layout detector reads by header name. Not yet checked against a real export from each portal |
| Vanta as evidence | Done offline: a failing test proposes the claim stale for its owner, never deprecates. The response shape is unverified against a live account |
| Vanta questionnaires received inside Vanta | Not built; needs the API and a test account |
| Governed Atlan context | Claims map to glossary terms with custom metadata, including product, deployment and data class (`scripts/atlan_setup.py`). Unverified against a tenant until 10 Nov |
| Product context | Done: a catalog fact never answers for AI features or the MCP server; a metadata claim never answers for customer data |
| Computed confidence | Done: every ANSWER carries a score, a band and one reason per factor; shown in the UI |
| Authoring claims from sources | Done: `/claims/author` and `POST /v1/claims/author[/upload]`, deterministic by default; the Haiku variant is tested offline only |

## What only Dhruv can do, in order

1. **Review and merge** `claude/fervent-zhukovsky-b6ef25` into `master`, then push. Nothing on this branch has been pushed.
2. **Record the first live evaluation** (step 8). With a key: `ANTHROPIC_API_KEY=... python evals/run_live.py`, then commit the record. This also makes the CI eval-record gate blocking rather than advisory.
3. **Deploy the hosted demo** (step 5): Render from `render.yaml`, Vercel from `vercel.json`, Supabase as `DATABASE_URL`. Seed with `scripts/seed_demo.py`, then run `scripts/smoke.py` against it and keep the output.
4. **Hand the runbook to someone else** (step 7) and time it.
5. **After 10 Nov, on the Atlan tenant**, only once the IP question in the plan is settled with Suhas: register the embedded app, take the JWKS URL, run `atlan_setup.py --create-cm` and confirm the multi-valued Options attributes, seed claims, run the smoke test. Use the `fde-install` skill.
6. **One case study**: one real questionnaire, one real company, before and after, signed off by a named GRC lead. Nothing architectural substitutes for it.

## Engineering follow-ups (not blocking a pilot)

- Calibrate confidence weights against reviewer edit rates per band once a tenant has four weeks of metrics.
- Holdout H11 and H12 are refused as `NO_COVERING_CLAIM` rather than held as `RELEVANCE_LOW`: safe, but worth a look with fresh holdout cases, never by tuning these two.
- Check one real OneTrust and one real Archer export against the layout detector, with fixtures.
- Decide the fate of the 59-prompt adversarial suite that lives only in the dangling commit `4c8bb86`: restore it against the current engine or delete the commit.
- Refresh `web/screenshots/` deliberately (the suite regenerates them with run-to-run differences).
