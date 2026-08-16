# TrustOps positioning (internal, names competitors; the site never does)

**Status: DRAFT for founder approval. Nothing here is public until Dhruv signs off.**

## One line

Security questionnaires answered from your approved evidence, with a citation on
every answer and a named gap on every refusal.

## The category and the wedge

Category: security questionnaire automation (buyers also search "CAIQ automation",
"vendor security review", "trust management").

Everyone in the category sells speed and an accuracy percentage. Conveyor leads with
95%+ first-pass accuracy. Vanta and Drata/SafeBase bundle questionnaire AI into
compliance platforms. All of them gate the first product experience behind a form or
a sales call.

The wedge is the remainder. 95% accurate means 1 in 20 answers is wrong, and a wrong
answer in a security questionnaire is a material misrepresentation in an enterprise
deal. TrustOps' release rule is zero unsupported claims, enforced by deterministic
gates outside the model, with refusal as a first-class outcome. The pitch line:

> Most tools answer confidently. TrustOps refuses correctly.

## Proof, not claims

- The public demo replays real engine output, recorded unchanged, including refusals.
- Anyone can sign up, upload their own documents, and watch ten questions get
  answered or refused in about two minutes. No call, no form gate. Nobody else in
  the category does this.
- Every deliverable is auditable: cited workbook, working paper, hash-chained log
  a customer can verify themselves.
- The eval suite is public on GitHub: planted traps for certification inference,
  contradictions, stale evidence, legal commitments, cross-tenant leakage.

## Competitor cheat sheet (for calls, never for the site)

| If they use | Their strength | Our counter |
|---|---|---|
| Conveyor | Best pure-play automation, portal autofill, high accuracy claims | Ask what happens to the wrong 5%. Show the refusal demo and the audit chain. |
| Vanta / Drata | Already own the compliance program | We answer from documents, not their platform; no rip-and-replace, works alongside. |
| SafeBase (Drata) | Deflection via trust center | Deflection helps until the buyer insists on their own workbook; that workbook is our product. |
| Spreadsheets + heroics | Free | Reviewer hours per questionnaire; our named-review queue keeps their control, removes their typing. |

## Data posture (say it exactly like this)

Retrieval runs on our server with a locally hosted index. The drafting model sees
one question and its retrieved excerpts, never full documents, never the document
list, never another tenant. Uploads are deleted 14 days after signup and never used
for training. Competitors answer this concern with vendor contracts; we answer it
with architecture.

## Pricing anchor (pilot conversations)

- Demo workspace: free, 3 runs, 14 days, fixed 10 questions.
- Pilot: paid, scoped to one real questionnaire end to end with their named
  reviewer. Anchor at the cost of the reviewer-hours it replaces, not at tooling
  price points. A 300-question DDQ at 10 minutes a question is 50 hours of a GRC
  lead's time; price the pilot against that.
- Do not publish pricing until two pilots have closed.

## Who buys, who uses, who blocks

- Buyer: head of GRC / security compliance lead at B2B SaaS, 50 to 2000 people,
  drowning in inbound questionnaires.
- User: the GRC analyst in the review queue, and sales engineering who wants the
  deal unblocked.
- Blocker: security itself ("another vendor holding our policies"). The custody
  section and the 14-day deletion exist for this conversation.
