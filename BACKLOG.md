# BACKLOG (append-only)

Findings from the 2026-08-16 three-assessor round table that were triaged below
the release gate. The loop exit criterion was zero CRITICAL and zero HIGH; these
are the MEDIUM and LOW items deliberately deferred, recorded so they are visible
rather than forgotten.

## Deferred: architecture and scale

- **Single-instance assumptions are load-bearing and undocumented at the boundary.**
  `review._lock` is process-local, the run queue is one in-process worker, and
  SQLite is a local file. All correct at `numInstances: 1`, all silently wrong at
  2. The audit chain can genuinely fork under a second instance. Before any scale
  out: key the lock by run directory, add an `flock` on `audit_log.jsonl`, and move
  the queue to the database.
- **Semantic index is pure-Python and rebuilt per run.** `index.json` stores vectors
  as decimal text and `search()` recomputes chunk tokenization on every query. At
  the advertised ceiling (20 docs x 200k chars) this is minutes of CPU and a 60MB+
  file inside the single worker. Cap chunks per tenant, store vectors binary,
  precompute chunk token sets at build time, and move index building off the run
  path. Currently mitigated only by small demo corpora.
- **Slug enumeration.** Workspace slugs derive from the org name, so `/t/acme` is
  guessable. Auth holds (the token is required and slug-bound), but the existence
  of a customer is disclosed to anyone who guesses. Low risk, worth a random suffix.
- **`runs.dir` stores an absolute host path** that couples the API response shape to
  on-disk layout.

## Deferred: product gaps before a paid pilot

- **OCR for scanned PDFs.** A meaningful share of real policies are scans;
  extraction fails closed with a clear message, which is correct but limiting.
- **Multi-reviewer roles and authenticated identity.** One bearer token per
  workspace means the GRC lead, the SME and the sales engineer share one credential
  and each type their own name. A pilot needs per-user login and roles so an
  approval cannot be forged. The demo discloses that reviewer identity is
  self-attested; that disclosure must remain until this ships.
- **Scale limits that a real DDQ breaks.** 20 documents, 5MB each, 3 runs, one
  worker at 6.5s per question. A 300-question questionnaire is ~33 minutes of
  pacing alone. Needs per-plan limits and a paid-tier model without free-tier RPM.
- **No re-run or diff when a policy is updated**, no delivery of the answered
  workbook back into the customer's process (email, Slack, portal), no billing,
  no support channel, no backup or restore of the SQLite disk, no monitoring
  beyond `/healthz`.

## Deferred: measurement and evidence

- **No live-drafter numbers anywhere.** Every published figure comes from the
  deterministic mock. Phase 1 of the original directive (recorded live-drafter
  fixtures, per-question token and cost telemetry, Langfuse behind an env flag)
  remains unbuilt. The public eval suite tests the drafter we do not ship in
  production.
- **No case study.** The single artifact that would disarm every objection is one
  real questionnaire, one real company, before and after, signed off by a named GRC
  lead. Nothing architectural substitutes for it.
- **Separate principled refusals from coverage gaps in the metrics.** A refusal
  because a gate fired (certification, contradiction, staleness, legal) and a
  refusal because retrieval missed are different products of the system and should
  never share a single blended rate. Publishing both numbers is a credibility
  advantage, not a weakness.

## Deferred: minor correctness

- `multipart.py`: a file body containing the client-chosen boundary silently
  truncates the part rather than erroring; duplicate field names last-win; no cap
  on part count.
- `load_env(ROOT)` re-reads `.env` and mutates `os.environ` on every run request,
  from a request thread, with no lock. Harmless in the container, still wrong.
- `db.connect()` opens a fresh connection with two PRAGMAs per call; a single
  status poll opens 3+N connections every 2 seconds.
- `test_runqueue.py` mutates the module-level queue without resetting it between
  tests. Inter-test pollution waiting to happen.
- Signup email is collected but never verified.

## Deferred from re-audit round 2 (2026-08-16)

- **The connection cap is a lateral move, not a fix.** `MAX_CONNECTIONS` bounds
  thread and memory growth, but the cap is global and non-queueing, so 64 held
  sockets return 503 to every caller including `/healthz`, and Render will cycle
  the instance on a failed health probe. A measured slowloris refreshes those
  sockets at ~2.2/s. Proper fix: exempt `/healthz` from the cap, and either queue
  briefly instead of rejecting, or move to a server that does not allocate a
  thread per connection.
- **`db.immediate()` is not reentrant.** No path nests it today, but 17 helpers
  in `server/` open their own connection, so the trap is one refactor away.
  `limits.signup_allowed` / `record_signup` are now dead production code that
  `tests/test_runqueue.py` still exercises: a racy API sitting next to the atomic
  one, which is how the next person reintroduces the bug.
- **`upload` commits the byte budget before writing the file** (`app.py`), so an
  ENOSPC (the exact condition the budget exists to prevent) leaves the row, the
  doc slot and the budget consumed with no file behind them. `delete_upload` got
  this ordering right; `upload` did not.
- **XFF handling assumes exactly one proxy.** Putting a CDN in front of Render
  makes the last hop the edge IP, so every client behind one edge shares a bucket
  of three. The 200/day global cap is what actually bounds abuse.
- **`semantic.build_index` writes `index.json` non-atomically** (plain
  `write_text`, unlike `extract.persist` which uses tmp+replace), so two runs for
  one tenant can race it. A torn read is swallowed and silently downgrades that
  run to lexical retrieval, which is at least recorded in `metrics["retrieval"]`.
- Nothing tests the connection semaphore or the expiry sweeper.
