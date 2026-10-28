# Rollback

Order matters: stop new intake, then roll the code, then restore state. Nothing here deletes claims in Atlan.

1. **Stop intake.** Set `CONSTAT_INTAKE_PAUSED=1` on the API (or scale it to zero). Tell the Slack channel.
2. **Roll the API image** to the previous tag. Health check: `GET /healthz`.
3. **Roll the web app** to the previous Vercel deployment.
4. **Sidecar database.** Restore the last Supabase snapshot if the schema changed; the schema is additive (`CREATE TABLE IF NOT EXISTS`), so a code rollback alone is usually enough.
5. **Claims in Atlan.** Leave the glossary and the custom metadata set in place. Proposals opened by the Vanta sync are pending items, not changes; reject them from the proposals page if they are wrong.
6. **Sent-answer log.** Never roll back. It is the record of what left the building.
7. **Model change.** If a model or prompt version is the cause, revert to the previous `evals/records/` entry's model id and prompt version; the CI gate requires a record for the new pair anyway.
8. **Resume intake** once the smoke test in `fde-install.md` step 9 passes.
