# DECISIONS.md (append-only)

- 2026-08-08 — Gates enforced in code, not prompt. Rejected: prompt-only guardrails (unauditable, drafter-dependent). Consequence: MockDrafter and AnthropicDrafter share identical safety posture.
- 2026-08-08 — Contradiction detection via declared frontmatter assertions (`assert.<key>`). Rejected for v0: NLI/semantic contradiction (non-deterministic, untestable as a hard gate).
- 2026-08-08 — Lexical retrieval for v0. Rejected: embeddings-first (opaque scoring; retrieval misses must fail closed anyway, and one deliberate miss (IVS-01.1) is kept in the demo as proof).
- 2026-08-08 — Cert-class claims require source type certificate/attestation even when a truthful "no" exists. Rationale: negative certification answers have deal consequences; phrasing belongs to a human (blueprint p.12).
- 2026-08-08 — Audit log = hash-chained JSONL over SQLite/DB. Rationale: tamper-evidence demoable in one pytest; DB adds nothing at this scale.
- 2026-08-08 — Demo auto-approval only for gate-clean complete-coverage drafts, explicitly labeled SIMULATED in log + report. Rejected: silent auto-approval (misrepresents the human-gate design).
- 2026-08-08 — Default live drafter = Haiku 4.5; gates make the cheap model safe. CONSTAT_MODEL env overrides.
- 2026-08-08 — Added GeminiDrafter as the $0 live option: Gemini free tier verified alive (no card, ~10 req/min — covers 24-question runs), OpenAI has no ongoing free API tier, Groq is the fallback alternative. Implemented over raw REST with stdlib urllib — rejected the google-genai SDK (needless install for one endpoint). Same system contract, same fail-closed parse, same gates. GEMINI_API_KEY / GEMINI_MODEL envs.
- 2026-08-08 — Client UI = zero-dependency stdlib web console (ui/app.py, one file, reuses the run-report design system). Rejected for v0: Streamlit review queue (extra install, heavier; stays Phase 2 per docs/CONSTAT_V0.md). The console is a thin client over the same pipeline the tests exercise — no separate answer path.
- 2026-08-08 — API keys via git-ignored .env (stdlib loader, re-read per request so a pasted key applies on page refresh). Rejected: python-dotenv (install for 20 lines) and shell exports (hostile to non-technical users). Keys are never logged and never committed.
- 2026-08-16 — Design system adopted from the owner's Claude Design project (f0b00150), by way of dhruv-portfolio/design-system/tokens. Ink/bone/signal palette plus the GRC status colours the portfolio defines but does not use; Constat is the product they were named for. Rejected: inventing a second palette for the tool (two systems to keep in sync, and the owner already resolved this one against real contrast measurements). Claude Design MCP (DesignSync) could not authorise in a web session, so tokens were taken from the committed export rather than the live project.
- 2026-08-16 — Brand typefaces (Newsreader, Archivo, Fragment Mono) ship with the package as subset woff2 inlined as data URIs. Rejected: a webfont CDN link, which made every run report depend on a third party staying up. A run report is an audit artefact that must render years later on a machine with no network, which is the dependency this product exists to remove. Cost is ~130KB per report; fallback to system stacks if the files are absent.
- 2026-08-16 — Brand copy rule adopted: no em dashes or en dashes in rendered copy. Enforced upstream by the portfolio's scripts/copy-gate.mjs, which the run report now passes on all 28 rules. Two of its rules are deliberately not honoured here: "classified" (the pipeline's own QState enum, not dossier theatre) and "embeddings" (a Phase 3 workstream in CONSTAT_V0.md, not a resume claim). Docstrings, comments and CLI text are out of scope; only rendered output is gated.
- 2026-08-16 — Founder override: the "no portal until paid pilot" rule (CONSTAT_V0.md, out-of-scope list) is rescinded. Building hosted multi-tenant self-serve: signup, evidence upload, live Gemini runs, named-reviewer queue, public landing. Render Starter, single instance. Rejected alternative: staying local-only with a static demo — the founder wants the demo to run on each prospect's own documents, which requires hosting.
- 2026-08-16 — Hosted runs generate a real workbook (constat/qgen.py) and feed the existing pipeline, rather than teaching run() a second questions-list input path. Keeps the certified ingest/export path singular and T6 structural guarantees free. Rejected: refactoring run() to accept a questions list (forks the constitution's fixture path).
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

## 2026-08-16 Round 4: the instrument round

The founder's brief after the refusal redesign landed: study UpGuard and the
top cybersecurity sites, then make the page "unreal, because people believe
what they see." Both reference URLs are egress blocked here, so the research
was triangulated by search. It converged on one lesson: UpGuard's liveliness
is an instrument, an instant security score that does something TO the visitor
in the first ten seconds. The 2026 retrospectives agree that embedded product
demos and scroll storytelling held up while WebGL spectacle did not.

Round 4 therefore made the visitor operate the product:

1. **Ask it yourself.** A question box over 49 precomputed real engine
   contracts (a 42 question bank plus the showcase seven), matched with a
   stemmed keyword matcher. On no match the demo refuses, which is what the
   engine would do. Everything shown is a verdict the engine actually returned.
2. **Tamper with the chain.** Six real audit log events recomputed live in the
   browser. The JS canonicaliser mirrors Python's json.dumps byte for byte,
   proven by the untouched chain verifying green in the page; the build
   asserts the recipe against AuditLog so drift fails the build. The visible
   label for the CLASSIFIED event reads ROUTED because the brand's dossier
   language rule wins on a marketing page; the event data underneath is
   verbatim, hashes and all.
3. **The pipeline, walked.** A token on a five station rail travels to where
   each trap strikes its question.
4. **The product, filmed.** A 30 second unedited Playwright screen capture of
   the real journey, 1.1MB VP8 inlined, poster from a distinct frame.

An adversarial three lens panel (conversion vs the UpGuard bar, design craft,
accessibility and performance) then audited the build. Their blocking findings
and what was done:

- Every CTA landed on a "not live yet" anti headline in the static build. The
  section is now "The hosted workspace opens shortly. Get in first." with a
  reserve CTA, the repo, and the two run-it-yourself commands. Static CTAs
  relabel to "Get early access"; the sample pack button points at the stage
  that actually replays the sample pack.
- The suggested placeholder question returned a refusal as the visitor's
  first hands on moment; it is now a question the engine cites cleanly.
- The reduced motion override on the stamp lost a specificity fight and the
  thud still ran; fixed by matching the animating selector.
- The auto advancing replay re announced the whole verdict block to screen
  readers every eleven seconds; the live region is now off during auto
  advance, polite only for user initiated shows, and the replay has a real
  pause button (WCAG 2.2.2).
- Pipeline station labels used the decoration only token at 4.26:1; now
  text tertiary.
- The tamper grid did not read as a chain; each block now names the hash it
  links back to, arrows cross the gutters at full width, and the broken state
  is a labelled wash rather than 7.5px text.
- Legal CSS leaked bare h2/h3 margins onto every card of the landing page;
  scoped to .legalwrap.
- Hotspot callouts could cover a neighbouring marker on a phone with no way
  out; outside tap now dismisses, markers repositioned onto the pixels their
  callouts describe, Escape closes, and each has a real accessible name.

Deliberately not adopted, with reasons: replacing LinkedIn intent messages
with mailto buttons (the founder chose LinkedIn precisely to see intent
before replying; the rights email stays); un-striking the hero's "or refused"
(the strike is the brand gesture the whole page performs); pruning the signup
CSS the static page does not use (the hosted build, which shares the
template, uses all of it).

Verified after the loop: all four instruments pass their Playwright probes,
167 tests, copy gate clean on all four rendered pages, zero console errors,
zero horizontal overflow at 1440 and 390, complete and coherent with
JavaScript disabled, first paint 240ms on the 2.1MB file with the video
fetching nothing until played.

## 2026-08-16 Round 5: the page was a document, not a pitch

Third round of design feedback and the first two had not landed. The founder:
"Sections have too much text. When I say too much, I mean actually too much. I
don't know how to cut off, or rather, what to cut off... if I was a buyer, I
don't know how I would understand anything about it. Complicated, very
complicated." And on the video: "just a scrolling video instead of transitions,
like a video created on Premiere Pro."

The audit made the complaint measurable: 2,082 visible words, 10.4 minutes of
reading, and 888 words before the first image or video. The h1 was a policy
statement, not a value proposition. My error, twice running, was answering
"more visual" by adding instruments rather than deleting sentences. Adding is
easier than cutting and it was the wrong move both times.

**Lead with the artefact.** The reader already has a mental model of a
spreadsheet, so the hero now renders five real rows of the delivered workbook,
read from examples/acme_security_questionnaire__DELIVERED.xlsx at build time:
two cited answers with their evidence pointers, two refusals naming the expired
and the conflicting documents, one routed to counsel. Engine text is verbatim;
em dashes normalize to commas at the rendering boundary only, because the brand
gate bans them and the engine's wording is not going to be changed to suit a
web page.

**Show one worked refusal, fold the rest.** The gates section went from 497
words to 111 by keeping the certification trap open (a founder instantly gets
"we said we are certified, we are not yet") and folding the other three behind
self-contained summaries.

**Move the knife to the front.** "Merged cells, hidden rows and formulas
survive untouched" was sitting at word 1,500. It is now the hero caption.

**Stop printing clipboard payloads.** The three contact prefill messages were
84 words of visible copy that only ever existed to be copied. They are off
screen now, still real text for the clipboard and for a screen reader.

Result: 890 visible words, 4.5 minute read, first visual at word 73, zero
visible paragraphs over 25 words, nine sections down to six.

**The video is now edited rather than recorded.** The system ffmpeg is
Playwright's, built --disable-everything: no drawtext, no zoompan, no xfade.
Installing imageio-ffmpeg brought a full static ffmpeg 7.0.2, which unlocked
H.264 and, more usefully, rawvideo demuxing, so composed frames return
losslessly instead of through a JPEG hop. Frames are composed in PIL with the
brand woff2 faces converted to TTF in memory, which buys pixel-exact typography
that a drawtext filter could not. The cut is 22.3s: title card, four act cards,
eight eased punch-ins sited inside windows where the page is not scrolling,
nine kinetic captions that type on, three cross-dissolves and a closing stat
card. The producing agent re-derived every beat from motion analysis rather
than trusting the timestamps I gave it, and found them about four seconds off.

**Two video sources, deliberately.** H.264 first for iOS Safari and Chrome,
VP9 WebM second for browsers built without the proprietary decoder. This was
not theoretical: the MP4 failed to play in Playwright's Chromium with
NotSupportedError, because Chromium-for-testing ships no proprietary codecs.
VP9 at crf 42 is visually indistinguishable from the H.264 master on the
caption frames and costs 0.95MB against VP8's 1.68MB, so the fallback is
cheaper than the thing it replaced. The page is 3.5MB with both.

Verified: 890 words, all instruments passing, 167 tests, copy gate clean on
four pages, zero console errors, zero overflow at 1440 and 390, coherent with
JavaScript disabled, reduced motion honoured, video autoplaying muted.
- 2026-08-25 — **Renamed the product TrustOps → Pramana → Constat**, and renamed the Python package with it (`pramana/` → `constat/`). *Constat*: French for an official written record of observed facts (a `constat d'huissier` is a bailiff's statement of what was verified), and Latin for "it is established". The domain is `constat.ai`; `constat.com`, `.io`, `.co`, `.app` and `.dev` are all taken. Rejected: keeping the package name frozen while renaming only the product, which is what was done for the TrustOps → Pramana step and which left the repository permanently disagreeing with itself about what it is called. Rejected also: `.com` alternatives — roughly 200 candidate names were checked and every meaningful single word was registered (`adduce`, `evince`, `factum`, `probity`, `indicia`, `fiducia`, `tessera`, `warranted`, `provably`, `defensible`, `attested`, `dossier`, `assay`), so a one-word `.com` is an aftermarket purchase rather than a registration.
- 2026-08-25 — **`tests/test_gates.py` was edited by the rename**, and this entry is the authorization the prime rule requires. Only the three `from pramana.… import` lines changed, to follow the package. No assertion, fixture, threshold or invariant was touched, and the suite was green before and after (238 passing). The prime rule exists to stop a failing gate being "fixed" by weakening its test; a module path following a rename is not that, and freezing the import path forever would be a worse outcome than recording the exception here.
- 2026-08-25 — **Prior entries in this log and in GOTCHAS.md were rewritten to say Constat.** Rejected: leaving the historical entries under the old names, which would have made the logs unreadable to anyone joining later, since the same component would appear under three names depending on the month. The names the product previously carried are TrustOps (to 2026-08-15) and Pramana (to 2026-08-25); that fact is recorded here so the rewrite is not silently revisionist.

- 2026-10-28 — Claims layer added beside the document pipeline (`constat/claims/`), not in place of it. The unit of truth becomes an owned, expiring, exception-carrying claim; questions match claims, not chunks; a new gate set (injection, legal, novelty, status, certification, relevance, parameter, completeness, absolutes, contractual) decides ANSWER / HOLD_HUMAN / REFUSE with a difficulty class per question. Rejected: rewriting the v0 pipeline in place, which would have voided the 239-test constitution for no gain while both layers are needed (documents are still where claims are born). Rejected: free-text exceptions inside the statement; a list is what makes the completeness gate checkable, which is the whole point of the telemetry-trap constraint.
- 2026-10-28 — ClaimStore is an interface with a file backend and an Atlan glossary backend through pyatlan (`constat/claims/atlan.py`). Writes are proposals until a second person approves; the author may not approve their own proposal. Rationale: the store should be swappable to Atlan's own glossary plus custom metadata after 10 Nov without a rewrite, and Atlan's MCP write tools already behave as propose-then-approve, so the file backend mirrors that contract rather than inventing a looser one. Rejected: building directly against a tenant now (none available before the start date).
- 2026-10-28 — Claim versions are content hashes, recorded on every sent answer and on every reused approved answer. Rationale: glossary terms mutate in place and have no immutable version; a hash pins what an answer rested on. Rejected: integer-only versions (a reviewer can bump them without a content change, and cannot prove what the old content was).
- 2026-10-28 — Process lessons taken from running a managed questionnaire service, kept as lessons only: ask the owner once and store the answer as a claim; leave blank rather than guess; every question carries an explicit state so a stuck or silently failed import is visible; bulk approval only for reused answers and only after spot checks; owners must be people, because knowledge bases decay through departed owners and blank scope. No service material, templates or client content were used.
- 2026-10-28 — Relevance is measured on the question's subject terms after removing value-asking words (how often, which version, cadence). Rationale: a claim that states a principle without the asked-for value is a parameter-missing case the owner can fix in one line, not an irrelevant claim; counting those words against it hid the more useful verdict. Found by golden case G14.
- 2026-10-28 — A claim covers a question only if it shares at least two subject terms with it (or half of a two-term question). Found by holdout case H07, where one shared verb ("offer") turned a novel passkeys question into a relevance hold against the encryption claim. H07 moved from holdout to dev because it has now informed the design; the holdout is not tuned against, so a case that changes the code leaves it.
- 2026-10-28 — Intake detects the questionnaire layout by header names, not by fixed positions, and finds the id column before the question column so "Question ID" is never mistaken for the question. The v0 fixtures still resolve to header row 3, columns A to E. Rejected: keeping `export.py`'s hard-coded layout as the only path (real questionnaires put the question anywhere). `export.py` stays untouched because the v0 tests are the constitution; the new path lives in `constat/intake/parsers.py`.
- 2026-10-28 — The normaliser is a model with no tools and no access to claims; its output is validated against a hand-written schema; a per-call canary turns an attempt to steer it into a quarantine signal; two failures fall closed to a HELD item that keeps the original text. Rejected: dropping unparseable items (a silently missing question is the failure mode managed questionnaire services suffer most) and a JSON-schema library (one dependency to validate five fields).
- 2026-10-28 — Drafting on claims forbids new values: any number, version or unit in the drafted answer that the claim does not state abstains the draft with NEW_VALUE_INTRODUCED before the gate runs. Rejected: trusting the prompt alone (the gate suite exists because prompts are not controls).
- 2026-10-28 — Item state machine with explicit transitions; every change writes a review action and a metric event. Illegal transitions raise. Rejected: free-form status strings (the challenge round's failure mode, hard questions piling up unseen, needs a state you can count).
- 2026-10-28 — The no-new-values rule moved from the model drafter into the gate, after the absolutes check, so a reviewer's edit is held to the same bar as a model draft: a number, version or unit the claim does not state holds the answer for the claim owner (found by the review tests: an edit inventing "every 7 days" had passed). "100% secure" is refused as an absolute first, not held as a value.
- 2026-10-28 — A stated cadence (annually, quarterly, monthly) counts as a value for the parameter gate; only digits did before, so "reviewed annually" was held as parameter-missing against a question asking for the review cadence.
- 2026-10-28 — Review actions: approve writes the answer back to the claim as an approved answer (the reuse corpus); an edit is re-gated and, when it changes more than 30% of the text, opens a proposal to the claim owner so the claim catches up with what reviewers actually say; bulk approval is for REUSED items only and refuses without spot checks of max(3, 10%). Rejected: silent writeback of edits into claim statements (a reviewer phrasing an answer is not the owner changing a fact).
- 2026-10-28 — Metrics are computed per difficulty class with the oldest open novel or contractual question per deal as the alarm and shipped-wrong as the stop signal; the human edit rate is the share of edits with any change plus the mean edit distance. Rejected: an overall automation rate on the dashboard (the brief names it as the failure mode).
- 2026-10-28 — Degradation is evaluated, not toggled: 72 hours without a decision action from the primary reviewer flips the tenant to degraded; transitions recorded under the same actor do not count as decisions. Degraded mode changes nothing about what may ship (the ladder decides that); it produces the AE status and the backup escalation list for deal-blockers. Rejected: lowering any gate while degraded.
- 2026-10-28 — The automation ladder is a pure decision function with the hard limits checked first, so no level can reach a contractual, novel, flagged, held or public-audience answer. L2 needs an approved customer and an unchanged, fresh claim; L3 needs four weeks of metrics with edit rate at or below 10% and zero shipped wrong.
- 2026-10-28 — A formula cell below a questionnaire's table (a footer total) is skipped with a warning; a formula inside a numbered row is read as text and quarantined. Found by the v0 structure fixture, whose COUNTA footer became a 25th question.
- 2026-10-28 — Vanta is the evidence spine, never the publisher: a failing test proposes the claim stale with a decision for the owner and a seven-day deadline; it never deprecates or unpublishes. Muted and missing tests are reported as findings. The sync is idempotent against open proposals. The Vanta response shape is parsed tolerantly and marked UNVERIFIED until checked against a live tenant.
- 2026-10-28 — The MCP server lives in `mcp_server/` (not `mcp/`, which would shadow the SDK package) and uses mcp 2.x's MCPServer with a FastMCP fallback. Tools are tagged [read] or [write] in their descriptions; writes return proposals; every call writes a metric event with the tool and caller. `answer_question` returns a verdict and says so in its payload, because an agent that treats it as a sent answer is the failure to design against.
- 2026-10-28 — The App Framework wrapper imports the SDK names from the docs and falls back to no-op decorators so the same plan runs in-process for tests. Rejected: blocking the wrapper on SDK access we do not have before 10 Nov.
- 2026-10-28 — Slack intake registers a request and asks the reviewer to upload the file; downloading from Slack needs a bot token and is not automated here. Notifications are Block Kit payloads built by pure functions.
- 2026-10-28 — Security review applied. Dev mode must be asked for (`CONSTAT_ENV=dev`); a process refuses to start with dev secrets outside dev or with Atlan JWTs accepted and no issuer; docs and openapi are off outside dev. The JWT tenant claim is validated as a slug and against an allowlist (one deployment serves one tenant by default); JWT principals are matched by source so a token cannot inherit a bearer principal's role; the JWKS client is cached. Rejected: scoping the claim store per tenant inside one process (a tenant is a deployment; the glossary is the tenant's).
- 2026-10-28 — Settings are read from the environment when `load()` runs, not as dataclass defaults at import, because the defaults froze the first process's values and hid a test-isolation bug.
- 2026-10-28 — Uploads: the declared length is checked first and the body read in chunks up to the cap; Office files are checked as zips (entries and inflated size) before any parser opens them; parsing runs off the event loop; event streams are capped per tenant and stop on disconnect; the detected layout is stored on the questionnaire row so export survives a restart.
- 2026-10-28 — Two exports. The customer export carries only SENT answers, generic notes, no owners, no flags, and neutralises cells that a spreadsheet would evaluate; the internal export (owner or admin) carries the working state. Rejected: one file for both audiences.
- 2026-10-28 — Every gate judges canonical text: NFKC, zero-width and format characters removed, number words as digits. Exceptions must carry their negation words. Mixed-script words are quarantined. The drafter sees the question inside a sentinel block marked as data and its output is screened for links, addresses and instructions to the reader. Found by the review's evasion cases; regex gates stay deterministic, which is the point, but they now see the text a person sees.
- 2026-10-28 — Web: the dev bearer and the shell simulator are dead code in production builds; the handshake accepts messages only from the framing window and locks the host origin after the first init; outside development the embed may be framed only by configured tenant origins, never by the Atlan wildcard.
- 2026-11-06 — Claims can be seeded from questionnaires already answered and sent, in two steps: a preview that screens, matches and gates every answered row and proposes an action (attach the answer to a covering claim, cluster rows into one draft claim, or skip with a named reason), and a commit where a person confirms. The commit trusts only the chosen action: question, answer and claim come from the stored preview, the screens and gates run again, and every new claim is a draft proposal a second person approves. An old answer is evidence of what was said, not proof that it is true; nothing here creates a verified claim. A past answer that conflicts with a verified claim is skipped with the conflict named, which is itself a finding for the owner.
- 2026-11-06 — **Claims carry product context** (`products`, `deployment`, `data_classes`, closed vocabularies in `constat/claims/scope.py`) and a gate after the usable check holds with `PRODUCT_SCOPE_MISMATCH` when the question names a product or data class the top claim does not cover. A fact about the catalog is not evidence about AI features, and a metadata claim is not evidence about customer data; for a vendor whose whole posture rests on "we hold metadata, not your data", that is the most expensive wrong answer available. Held, not refused: the owner can confirm the claim extends in one line. A declared list is authoritative; an empty one falls back to what the claim's own statement and scope name (never its exceptions, so "excludes prompts" cannot make a claim cover prompts). Rejected: empty means everything (every legacy claim would answer for every product, which is the failure being fixed); empty means nothing (every legacy claim holds on every "customer data" question, most of the set, and reviewers learn to click through holds). The fields join the version hash only when declared, so hashes recorded on sent answers before this change still verify. The matcher boosts claims that cover the named scope and, on a tie for a question naming none, prefers the broader claim (found by `test_mcp::test_search_and_freshness` once a catalog-scoped at-rest claim joined the fixture). Not done: holding a product-scoped claim against a question that names no product; the answer names its own scope, so the reader is not misled, and the relevance gate already judges narrowness. `deployment` is carried but not gated yet. Golden cases G23 to G30, holdout H09 and H10; Atlan custom metadata as Options attributes (multi-valued for products and data classes, UNVERIFIED against a live tenant).
- 2026-11-06 — **Claim-drafting assistant** (`constat/claims/author.py`, `POST /v1/claims/author`): a source document with an id and version becomes draft claims, one fact each, each citing the exact span it came from as `source vVERSION [start:end] "quote"`, opened through `store.propose` so a second person approves. It never sees a question or the claim store's contents and never answers. The deterministic sentence extractor is the default; it keeps present-tense, fact-shaped sentences, skips questions, how-to steps, plans, marketing, code, tables and anything the intake screen quarantines, each with a named reason, and folds an exception sentence ("This does not apply to...") into the fact before it. The Haiku variant sits behind the same interface with the normaliser's pattern (no tools, hand-written schema, per-call canary, fail closed), and a source that screens as instructions never reaches the model. Both are held to one check: the quote must occur verbatim in the source (whitespace aside) and the statement may state no number, version or unit its quote does not; a fact whose exception fails that check is dropped whole, because a fact without its exception is the telemetry trap. An extracted sentence may never cite certificate-class evidence: a document saying "we are certified" is not the certificate, so the certification gate still holds it. Rejected: letting the model write claims straight into the store (an extracted sentence is what a document says, not proof it is true); one claim per paragraph (fails the one-fact rule and makes the completeness gate meaningless); fuzzy quote matching (a paraphrased quote is exactly the hallucination the span exists to catch). The Haiku variant is tested offline against recorded replies only; no live run and no `evals/records/` entry exists yet, because no API key was available, and `author.py` is now on the eval-record watch list so its first prompt change must ship one. Golden set `evals/author/cases.json` (18 cases, zero dangerous) over a synthetic corpus paraphrased from public docs.atlan.com pages named in `evals/author/sources.json`, plus an Acme noise document.
- 2026-11-06 — **"REST API" is one token, not "rest"** (`claims/match.py: key_terms`). Found by the authored corpus: the MCP claim "fetches metadata live from Atlan's REST APIs" covered half of "Is data processed by the MCP server encrypted at rest?" and answered it. Rejected: a stop-word for "rest" (it would blind every at-rest question). Still open, and not tuned here: a claim that shares two subject nouns with a five or six term question passes the 50% relevance bar even when it does not answer the asked property (an MCP "keeps no copy" claim answers "is metadata handled by the MCP server encrypted at rest?"). It needs its own golden cases before the threshold moves.
- 2026-11-06 — **PDF questionnaire intake** (`intake/parsers.py: parse_pdf`): numbered items, id-numbered items (`AC-01 ...`) and question-shaped lines become RawQuestions, sharing one heuristic with `parse_docx`; a pdf question with no number gets a page-scoped id (`p2.3`). Wrapped lines rejoin only when the item has not ended its sentence and the next line starts lower case; running headers, footers and page markers are dropped. Rejected: reusing the evidence paragraphizer (`server/extract.py`), which keeps a full-width line ending in "?" open and merged consecutive questions; that heuristic is right for policy prose, wrong for a questionnaire. The size guard is the pdf equivalent of `check_zip` and runs before any text is extracted: encrypted files, more than 100,000 declared objects or 400 pages, or content streams whose decoded size passes the same 64MB budget as an inflated Office file are refused, then extracted text is capped at 2 million characters as it accumulates; pypdf's own per-stream limit stays underneath. Rejected: trusting the 6MB upload cap (a small flate stream inflates without bound, which is why the zip check exists). A line that opens like a question ("Do you...") is no longer taken for a section heading in either format. Injection cases P01 to P04 lay attacks out as PDF lines (split across a wrap, in a continuation line, inside an id-numbered item, between a header and a page marker) and require the parsed question to be quarantined, so the re-joiner cannot launder an attack and the parser cannot drop one silently.
- 2026-11-06 — **Relevance judges the property and the subject apart** (`claims/properties.py`, step 5 of `claims/gates.py`). Closes the gap left open in the REST entry above. Half the words in common was coverage even when the shared half was only the subject ("is customer data in transit logged?" answered with the TLS claim; "are laptops backed up?" with the endpoint claim; "is metadata handled by the MCP server encrypted at rest?" with the "keeps no copy" claim) or only the property ("are audit logs encrypted at rest?" answered with the customer-data at-rest claim). Now every property family the question asks about (a closed list of nineteen: encryption, at rest, in transit, logging, backup, retention and so on) must appear in the claim's statement, scope, keywords or exceptions, and when it does, at least one of the question's other subject terms must be shared; either miss holds with `RELEVANCE_LOW` and a gap naming what was missing. Families match the matcher's stems, which keeps the verb from the noun ("logged" is logging, "audit logs" is a subject). Exceptions count, because "backups in the legacy archive are encrypted with AES-128" is a statement about backups. Written test-first: G31 to G37 went in red with seven dangerous failures (commit 80870d7), G38 to G40 are positive controls, and every earlier case still passes. Rejected: raising RELEVANCE_MIN (it moves every case at once and still cannot tell the subject from the property); a model judge for relevance (the gates stay deterministic on purpose). Holdout H11 and H12, written before the fix, are refused as NO_COVERING_CLAIM before relevance runs: safe, reported, not tuned against. A property outside the list is still counted as a subject word, which is the old behaviour.
- 2026-11-06 — **Every ANSWER carries a computed confidence** (`claims/confidence.py`, `Verdict.confidence = {score, band, factors, basis}`); HOLD and REFUSE carry none, because there is no answer to be confident in. Four factors from facts the gates already read: relevance (share of subject terms covered, 0.40), evidence class (machine-checked 1.0, certificate 0.9, controlled document 0.75, bare statement 0.5; 0.25), freshness (decays inside 30 days of expiry; 0.15) and provenance (a verbatim reuse of a person-approved answer 1.0, a fresh draft 0.7; 0.20). Bands: high at 0.85, medium at 0.70. Each factor comes with the sentence the reviewer sees. Confidence orders reading; it never changes an outcome, and by construction a drafted answer resting on a bare statement cannot reach high. Rejected: a model's self-reported confidence (uncalibrated, and the gates exist because a model's view of itself is not a control); folding confidence into release (the gates decide release, and a threshold on a weighted sum would be a second, blurrier gate). The golden runner now requires confidence on every ANSWER and its absence elsewhere; G12 (reused, documented) pins high and G28 (statement-only evidence) pins medium. The weights are a starting point to calibrate against reviewer edit rates per band once the tenant has four weeks of metrics.
- 2026-11-06 — **The install smoke test is a script** (`scripts/smoke.py`), not a ten-minute manual walk: twelve checks over the API with the stdlib only (healthz; upload; processing finishes; REVIEW, HELD and REFUSED reached with nothing SENT; the legal question held for LEGAL; a computed confidence on every draft; one approve and send; the customer export holds that answer and no internal cells; an injection asked through the palette is refused; metrics with zero shipped wrong; degradation mode normal). Run in-process by `tests/test_smoke.py` and verified over real HTTP against a local uvicorn. Rejected: a pytest plugin an FDE would have to install, and a shell script of curl calls (the multipart upload and the xlsx export check are where curl scripts rot). The manual steps stay in the runbook as the fallback. Also removed the `data-hosted/pramana.db*` files left by the rename; nothing referenced them.
- 2026-11-06 — **The web app shows computed confidence and product scope, and CI now gates the web app.** `VerdictCard` renders the band and score beside the difficulty and a collapsed "why" list with one sentence per factor, on every surface including the review page; held and refused verdicts show none. The claim page shows declared products and data classes. Types are additive and optional (`Verdict.confidence`, `Claim.products/data_classes/deployment`, `ImportRow.products/data_classes`) so a server that predates them still renders. Verified against the live engine (review page shows "medium confidence 0.79" with its four reasons, zero console errors) and by the full Playwright suite (90 passed), with a new assertion that an ANSWER carries a confidence pill and a HOLD does not. The plan's CI line for the web (lint with the copy gate, typecheck, unit tests, Playwright smoke) had never been wired; it is now a second job. Rejected: committing the screenshots the suite regenerates (pages untouched by this change differed run to run, which is noise in review). Not done here: a screen for `POST /v1/claims/author`; the route and types exist, the authoring UI is the web owner's next screen.
