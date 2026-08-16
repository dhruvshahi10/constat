# DECISIONS.md (append-only)

- 2026-08-08 — Gates enforced in code, not prompt. Rejected: prompt-only guardrails (unauditable, drafter-dependent). Consequence: MockDrafter and AnthropicDrafter share identical safety posture.
- 2026-08-08 — Contradiction detection via declared frontmatter assertions (`assert.<key>`). Rejected for v0: NLI/semantic contradiction (non-deterministic, untestable as a hard gate).
- 2026-08-08 — Lexical retrieval for v0. Rejected: embeddings-first (opaque scoring; retrieval misses must fail closed anyway, and one deliberate miss (IVS-01.1) is kept in the demo as proof).
- 2026-08-08 — Cert-class claims require source type certificate/attestation even when a truthful "no" exists. Rationale: negative certification answers have deal consequences; phrasing belongs to a human (blueprint p.12).
- 2026-08-08 — Audit log = hash-chained JSONL over SQLite/DB. Rationale: tamper-evidence demoable in one pytest; DB adds nothing at this scale.
- 2026-08-08 — Demo auto-approval only for gate-clean complete-coverage drafts, explicitly labeled SIMULATED in log + report. Rejected: silent auto-approval (misrepresents the human-gate design).
- 2026-08-08 — Default live drafter = Haiku 4.5; gates make the cheap model safe. PRAMANA_MODEL env overrides.
- 2026-08-08 — Added GeminiDrafter as the $0 live option: Gemini free tier verified alive (no card, ~10 req/min — covers 24-question runs), OpenAI has no ongoing free API tier, Groq is the fallback alternative. Implemented over raw REST with stdlib urllib — rejected the google-genai SDK (needless install for one endpoint). Same system contract, same fail-closed parse, same gates. GEMINI_API_KEY / GEMINI_MODEL envs.
- 2026-08-08 — Client UI = zero-dependency stdlib web console (ui/app.py, one file, reuses the run-report design system). Rejected for v0: Streamlit review queue (extra install, heavier; stays Phase 2 per docs/PRAMANA_V0.md). The console is a thin client over the same pipeline the tests exercise — no separate answer path.
- 2026-08-08 — API keys via git-ignored .env (stdlib loader, re-read per request so a pasted key applies on page refresh). Rejected: python-dotenv (install for 20 lines) and shell exports (hostile to non-technical users). Keys are never logged and never committed.
- 2026-08-16 — Design system adopted from the owner's Claude Design project (f0b00150), by way of dhruv-portfolio/design-system/tokens. Ink/bone/signal palette plus the GRC status colours the portfolio defines but does not use; Pramana is the product they were named for. Rejected: inventing a second palette for the tool (two systems to keep in sync, and the owner already resolved this one against real contrast measurements). Claude Design MCP (DesignSync) could not authorise in a web session, so tokens were taken from the committed export rather than the live project.
- 2026-08-16 — Brand typefaces (Newsreader, Archivo, Fragment Mono) ship with the package as subset woff2 inlined as data URIs. Rejected: a webfont CDN link, which made every run report depend on a third party staying up. A run report is an audit artefact that must render years later on a machine with no network, which is the dependency this product exists to remove. Cost is ~130KB per report; fallback to system stacks if the files are absent.
- 2026-08-16 — Brand copy rule adopted: no em dashes or en dashes in rendered copy. Enforced upstream by the portfolio's scripts/copy-gate.mjs, which the run report now passes on all 28 rules. Two of its rules are deliberately not honoured here: "classified" (the pipeline's own QState enum, not dossier theatre) and "embeddings" (a Phase 3 workstream in PRAMANA_V0.md, not a resume claim). Docstrings, comments and CLI text are out of scope; only rendered output is gated.
- 2026-08-16 — Founder override: the "no portal until paid pilot" rule (PRAMANA_V0.md, out-of-scope list) is rescinded. Building hosted multi-tenant self-serve: signup, evidence upload, live Gemini runs, named-reviewer queue, public landing. Render Starter, single instance. Rejected alternative: staying local-only with a static demo — the founder wants the demo to run on each prospect's own documents, which requires hosting.
- 2026-08-16 — Hosted runs generate a real workbook (pramana/qgen.py) and feed the existing pipeline, rather than teaching run() a second questions-list input path. Keeps the certified ingest/export path singular and T6 structural guarantees free. Rejected: refactoring run() to accept a questions list (forks the constitution's fixture path).
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
