---
name: fde-install
description: Walk an Atlan field engineer through installing Constat on a tenant using docs/runbooks/fde-install.md, checking each step's output. Use when asked to "install Constat", "set up the tenant", "deploy to Atlan".
---

# FDE install

Follow `docs/runbooks/fde-install.md` step by step. At each step:

- Run the command, show the output, and compare it to the expected result in the runbook.
- Never paste secrets into chat; refer to them by variable name.
- If `scripts/atlan_setup.py --dry-run` shows fewer terms than the claims file, stop: the seeder refused a claim and printed why.
- If the API refuses to start, read the message: it names the setting (dev token outside dev, missing issuer). Fix the environment, do not change the code.
- The smoke test (step 9) is the definition of done. Report its six checks as a table.

At the end, write the install record: tenant slug, API host, web origin, glossary name, date, the model id from `/v1/evals/records`.
