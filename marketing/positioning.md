# Constat positioning (internal, names competitors; the site never does)

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
deal. Constat' release rule is not a percentage and not a promise about the model.
It is a gate: an answer is released only if it survives citation checking and its
words are traceable back to the passage it cites. Everything else is refused, with
the gap named and an owner attached. Refusal is a first-class outcome, not an error
state. The pitch line:

> Most tools answer confidently. Constat refuses correctly.

## Proof, not claims

- The public demo replays real engine output, recorded unchanged, including refusals.
- Anyone can sign up, upload public evidence, and watch ten questions get answered
  or refused in about two minutes. No call, no form gate. Nobody else in the
  category does this.
- What "public evidence" means, and why we say it out loud: the free demo drafts on
  Google Gemini's free tier, whose terms permit Google to use submitted content to
  improve their services. So the demo asks for documents that are already published:
  a public SOC 2 report, an ISO certificate, trust-center policy pages. Confidential
  evidence belongs on the BYOK or Managed tier, where the provider terms are yours.
- Every deliverable is auditable: cited workbook, working paper, hash-chained log
  a customer can verify themselves.
- Every provenance line is the customer's own document text. The drafting model is
  never allowed to author the excerpt shown under an answer, and a citation it
  invents is dropped before the answer is scored.
- The eval suite is public on GitHub: planted traps for certification inference,
  contradictions, stale evidence, legal commitments, cross-tenant leakage,
  fabricated citations, and answers that drift away from what they cite.

## Competitor cheat sheet (for calls, never for the site)

| If they use | Their strength | Our counter |
|---|---|---|
| Conveyor | Best pure-play automation, portal autofill, high accuracy claims | Ask what happens to the wrong 5%. Show the refusal demo and the audit chain. |
| Vanta / Drata | Already own the compliance program | We answer from documents, not their platform; no rip-and-replace, works alongside. |
| SafeBase (Drata) | Deflection via trust center | Deflection helps until the buyer insists on their own workbook; that workbook is our product. |
| Spreadsheets + heroics | Free | Reviewer hours per questionnaire; our named-review queue keeps their control, removes their typing. |

## Product tiers (the honest answer to "where does my evidence go")

| Tier | Whose key | What to upload | Provider terms |
|---|---|---|---|
| Demo | Ours, Google Gemini free tier | Public evidence only: a published SOC 2 report, an ISO certificate, trust-center policy pages | Google's free-tier terms permit them to use submitted content to improve their services. That is why the demo is scoped to documents that are already public. |
| BYOK | Yours | Your confidential evidence | Whatever your contract with your provider says. We hold no copy of your key beyond the run, and your text goes to your account, not ours. |
| Managed | Ours, paid | Your confidential evidence | Paid provider tier carrying a no-training commitment, passed through to you in writing. |

The tier is the answer to the security question, not a paragraph of reassurance.
If someone on a call asks "is our data used for training", the answer is: on the
free demo, assume yes, which is why we tell you to upload public documents; on BYOK
and Managed, no, and here is the contract that says so.

## Data posture (say it exactly like this)

Retrieval runs on our server with a locally hosted index. The drafting model sees
one question and its retrieved excerpts, never full documents, never the document
list, never another tenant. Each excerpt is capped before it is transmitted, and the
run report prints the character count sent per question, so the custody claim is a
receipt rather than an assurance. Uploads are deleted 14 days after signup.

Sub-processors, named plainly: Google Gemini for drafting, Render for hosting. There
are no others. Competitors answer this concern with vendor contracts; we answer it
with architecture first and then the contract.

## Pricing anchor (pilot conversations)

- Demo workspace: free, 3 runs, 14 days, fixed 10 questions, public documents only.
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
- Blocker: security itself ("another vendor holding our policies"). The tier table,
  the named sub-processor list, the per-question custody receipt and the 14-day
  deletion exist for this conversation. Lead with BYOK; a security team that can
  point the engine at its own provider account stops being a blocker.
