# DECISIONS.md (append-only)

- 2026-08-08 — Gates enforced in code, not prompt. Rejected: prompt-only guardrails (unauditable, drafter-dependent). Consequence: MockDrafter and AnthropicDrafter share identical safety posture.
- 2026-08-08 — Contradiction detection via declared frontmatter assertions (`assert.<key>`). Rejected for v0: NLI/semantic contradiction (non-deterministic, untestable as a hard gate).
- 2026-08-08 — Lexical retrieval for v0. Rejected: embeddings-first (opaque scoring; retrieval misses must fail closed anyway, and one deliberate miss (IVS-01.1) is kept in the demo as proof).
- 2026-08-08 — Cert-class claims require source type certificate/attestation even when a truthful "no" exists. Rationale: negative certification answers have deal consequences; phrasing belongs to a human (blueprint p.12).
- 2026-08-08 — Audit log = hash-chained JSONL over SQLite/DB. Rationale: tamper-evidence demoable in one pytest; DB adds nothing at this scale.
- 2026-08-08 — Demo auto-approval only for gate-clean complete-coverage drafts, explicitly labeled SIMULATED in log + report. Rejected: silent auto-approval (misrepresents the human-gate design).
- 2026-08-08 — Default live drafter = Haiku 4.5; gates make the cheap model safe. TRUSTOPS_MODEL env overrides.
- 2026-08-08 — Added GeminiDrafter as the $0 live option: Gemini free tier verified alive (no card, ~10 req/min — covers 24-question runs), OpenAI has no ongoing free API tier, Groq is the fallback alternative. Implemented over raw REST with stdlib urllib — rejected the google-genai SDK (needless install for one endpoint). Same system contract, same fail-closed parse, same gates. GEMINI_API_KEY / GEMINI_MODEL envs.
- 2026-08-08 — Client UI = zero-dependency stdlib web console (ui/app.py, one file, reuses the run-report design system). Rejected for v0: Streamlit review queue (extra install, heavier; stays Phase 2 per docs/TRUSTOPS_V0.md). The console is a thin client over the same pipeline the tests exercise — no separate answer path.
- 2026-08-08 — API keys via git-ignored .env (stdlib loader, re-read per request so a pasted key applies on page refresh). Rejected: python-dotenv (install for 20 lines) and shell exports (hostile to non-technical users). Keys are never logged and never committed.
- 2026-08-16 — Design system adopted from the owner's Claude Design project (f0b00150), by way of dhruv-portfolio/design-system/tokens. Ink/bone/signal palette plus the GRC status colours the portfolio defines but does not use; TrustOps is the product they were named for. Rejected: inventing a second palette for the tool (two systems to keep in sync, and the owner already resolved this one against real contrast measurements). Claude Design MCP (DesignSync) could not authorise in a web session, so tokens were taken from the committed export rather than the live project.
- 2026-08-16 — Brand typefaces (Newsreader, Archivo, Fragment Mono) ship with the package as subset woff2 inlined as data URIs. Rejected: a webfont CDN link, which made every run report depend on a third party staying up. A run report is an audit artefact that must render years later on a machine with no network, which is the dependency this product exists to remove. Cost is ~130KB per report; fallback to system stacks if the files are absent.
- 2026-08-16 — Brand copy rule adopted: no em dashes or en dashes in rendered copy. Enforced upstream by the portfolio's scripts/copy-gate.mjs, which the run report now passes on all 28 rules. Two of its rules are deliberately not honoured here: "classified" (the pipeline's own QState enum, not dossier theatre) and "embeddings" (a Phase 3 workstream in TRUSTOPS_V0.md, not a resume claim). Docstrings, comments and CLI text are out of scope; only rendered output is gated.
- 2026-08-16 — Founder override: the "no portal until paid pilot" rule (TRUSTOPS_V0.md, out-of-scope list) is rescinded. Building hosted multi-tenant self-serve: signup, evidence upload, live Gemini runs, named-reviewer queue, public landing. Render Starter, single instance. Rejected alternative: staying local-only with a static demo — the founder wants the demo to run on each prospect's own documents, which requires hosting.
- 2026-08-16 — Hosted runs generate a real workbook (trustops/qgen.py) and feed the existing pipeline, rather than teaching run() a second questions-list input path. Keeps the certified ingest/export path singular and T6 structural guarantees free. Rejected: refactoring run() to accept a questions list (forks the constitution's fixture path).
- 2026-08-16 — AuditLog.resume() refuses to append to a chain that fails verification. Appending fresh valid links after tampering would launder the tampering; fail closed instead.
- 2026-08-16 — Semantic retrieval ships with two backends behind one interface: fastembed bge-small (production, baked into the Docker image at build time so runtime has zero egress) and a stdlib hashed character n-gram embedder plus a small generic GRC synonym/stem bridge (the always-available floor, which alone flips IVS-01.1). Rejected: model-only (unverifiable here — HuggingFace is egress-blocked in this dev environment, so the bge path is first exercised by the Render image build) and sentence-transformers (torch cannot fit a 512MB instance).
- 2026-08-16 — Per-tenant index is rebuilt before each run rather than maintained at upload. One code path, never stale, cheap at demo corpus sizes. Rejected: index-on-upload (a second consistency surface for no measurable win at this scale).
- 2026-08-16 — Grounding gate threshold set at 0.35 content-word overlap with a 4-token floor. Measured, not guessed: faithful answers from the deterministic drafter score 0.65 to 0.94, unrelated text 0.0 to 0.15, so 0.35 sits in the empty band at roughly half the observed floor. Rejected: a higher threshold (refuses legitimate paraphrase) and NLI-based entailment (a second model to trust, when the whole point of the gates is that they are deterministic and auditable). Known and disclosed in README: the gate is lexical, so it catches fabrication and drift but not negation, and the calibration comes from a drafter that quotes chunk text verbatim rather than one that paraphrases.
- 2026-08-16 — Assertion extraction ships with a "not our commitment" filter that drops any sentence quoting law, stating a third party's duty, or scoped to a non-production case. A re-audit reproduced the failure it prevents: a GDPR Article 33 quotation, boilerplate in nearly every incident response plan, was extracted as a 72-hour notification commitment, collided with the vendor's own 24-hour promise, quarantined both documents and told the customer their correct policies contradicted each other. Rejected: shipping the extractor as-was and relying on the intra-document conflict check, which does not fire across documents. The filter is deliberately over-broad; it costs true positives (a sentence merely mentioning a subprocessor is now skipped) to avoid a false accusation attached to a customer's own document owners.
- 2026-08-16 — unsupported_material_claims is retained as a tripwire and removed from every rendered surface. It is zero by construction (post_gate nulls the answer whenever no citation survives), so presenting it as a measurement was a tautology an audit correctly called out. The run report and the local console now show ungrounded_refusals and citations_dropped, which vary. Rejected: deleting the metric, since a future change that lets an answer past the citation rule should still show up as a non-zero somewhere.
- 2026-08-16 — Jurisdiction resolved to India without asking the founder again. He said he did not know how to tackle it, which was fair: I had posed a legal-sounding question when it was a factual one, and the fact was already published in his own portfolio (Bengaluru and Delhi NCR, plus an existing reference to India DPDP). Governing law and venue are India; the privacy page names the DPDP Act 2023 and the Data Protection Board of India as the complaint route, with GDPR retained for EU and UK visitors. The founder-drafted banner stays: a security reviewer would rather see it than a false claim of counsel.
- 2026-08-16 — Every contact CTA moved to LinkedIn, with one deliberate exception. LinkedIn has no reliable URL parameter to prefill a message body, so promising a prefilled DM would have shipped a dead button; instead the page offers three intent-tagged messages that copy to the clipboard, are selectable text when the clipboard is blocked, and open the profile. The exception is data-rights requests, which keep an email address, because telling a data subject their only channel for a DPDP or GDPR right is a social DM would not survive scrutiny.
- 2026-08-16 — Added a --static single-file build rather than relative legal links. The absolute /site/legal/ href form made static hosting unresolvable (publishing site/ as root 404s the legal links; publishing the repo root buries index.html), and a published artifact is one file where a separate legal/terms.html cannot exist at all. Inlining Terms and Privacy as #terms and #privacy sections from the same TERMS_BODY and PRIVACY_BODY constants fixes every case at once and keeps one source of truth. The static build asserts it contains no /api/signup, no /site/legal/ and no placeholders, so it cannot silently regress into needing a backend.

## 2026-08-16 The landing page was a research paper, and it was my fault

The founder's verdict on the first published landing page: "very less visual,
very less 2026 modern UI... It looks like a research paper." He was right, and
the diagnosis was specific rather than a matter of taste.

1. Roughly half the rendered page was inlined legal text, which I had added the
   same round when `build_static` learned to inline Terms and Privacy as open
   sections. Solving the single-file problem made the marketing page a document.
2. Six consecutive sections shared one shape: eyebrow, heading, paragraph, row
   of bordered cards. That repetition is the generic pattern, and no amount of
   good copy survives it.
3. There were zero images, on a product that has three working screens.

What changed, and why each one is a claim rather than a decoration:

- **The page performs a refusal instead of describing one.** Each of the four
  traps now shows the confident answer a competitor would have shipped, struck
  through in the refusal colour as the card arrives, with the gate's stamp
  landing on it. The gate reasoning is plain text underneath, always visible;
  the hover-to-reveal redaction bars are gone, which also retires the finding
  that they were unreachable on touch.
- **`--status-critical` is promoted to a co-lead colour.** The product's
  argument is the refusal, so the refusal needed a colour of its own rather than
  a chip on a grey card. Signal still leads for what gets released.
- **Real screenshots.** `site/img/*.jpg` are captures of a live hosted run
  (tenant "Northwind Systems"), inlined as data URIs from `site/img/shots.json`
  so the page remains one self-contained file with zero external requests. The
  full-resolution PNG sources are gitignored; the JPEGs are the committed
  originals.
- **Legal is folded.** The static build now emits both documents inside
  `<details>` rather than as open sections. `<details>` over `<dialog>` because
  it needs no JavaScript to open, and an in-page anchor link opens the document
  it names through one small handler. Both texts are still present in full, from
  the same `TERMS_BODY` / `PRIVACY_BODY` the hosted pages use.
- **The struck line and the stamp are drawn by default and hidden only when
  scripting is on.** Without that inversion, a no-JS reader saw four cards whose
  entire point was invisible.

One build hazard hardened: `build_static` locates the backend JS by a
box-drawing comment marker, and a CSS section header using the same words made
`replace(count=1)` hit the stylesheet instead. It has now bitten twice, so the
build asserts the marker occurs exactly once rather than guessing.

Verified: 167 tests passing, brand copy gate clean on all four rendered pages
(one rewrite needed, "classified" tripped the dossier-language rule), zero
horizontal overflow and zero console errors at 1440px and 390px, both legal
disclosures reachable with scripting disabled, and the hosted build unchanged
in the way that matters (signup form intact, legal links still absolute).
