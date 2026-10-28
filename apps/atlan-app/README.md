# Constat App Framework wrapper

Runs the Constat pipeline inside Atlan's app runtime: ingest a questionnaire,
match and draft against the claims in the "Security Claims" glossary, notify
Slack with the counts. Reviewers then work the queue in the embedded app.

- `app.py`: the App with three tasks (ingest, match_and_draft, notify). Without the
  SDK the same plan runs in-process (`run_locally`), which is how it is tested.
- `Dockerfile`: multi-platform image on Atlan's `app-runtime-base`.
- Install steps live in `docs/runbooks/fde-install.md`.

The SDK import names follow docs.atlan.com; if the installed `application_sdk`
version names them differently, change the one import block at the top of `app.py`.
