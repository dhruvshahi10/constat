---
name: golden-case
description: Add a case to Constat's golden set (evals/golden/cases.json) or injection suite (evals/injection/cases.json), run it, and report. Use when asked to "add an eval case", "cover this in the golden set", "this should be refused".
---

# Golden case

1. Decide the suite: a verdict expectation goes to `evals/golden/cases.json`; an attack string goes to `evals/injection/cases.json`.
2. For a golden case set `id` (next G or H number), `split` (`dev` unless it is a paraphrase of an existing dev case, then `holdout`), `weight` (3 when a wrong ANSWER would reach a customer, 2 for a wrong hold, 1 otherwise), `domain`, `audience`, `question`, optional `candidate_answer`, and `expect` with `outcome`, optional `flag`, `difficulty`, `route`, `answer_contains`.
3. If the case needs a claim that does not exist, add it to `evals/golden/claims_acme.json` with the `claim-author` rules; synthetic data only.
4. Run `python evals/run_golden.py --split all --verbose` (or `python evals/run_injection.py --verbose`). Zero dangerous failures is the release rule.
5. If the case fails and the code is wrong, fix the code and add a DECISIONS.md line naming the case. If the case moved a holdout item into the design, move it to `dev` and say so.
6. Report the case id, the outcome, and what changed.
