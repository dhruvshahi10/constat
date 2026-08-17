# LinkedIn launch post (DRAFT for founder approval and personal voice pass)

---

Every AI security questionnaire tool I evaluated leads with an accuracy percentage.
95%, 96%, "nearly perfect."

Here is the problem with that sentence: a security questionnaire is not a quiz.
Every answer is a representation your company makes in a deal. 95% accurate means
1 in 20 answers is wrong, in writing, to a customer's security team.

So I built the opposite.

Pramana AI answers security questionnaires from your own approved documents, and its
headline is not an accuracy number. An answer is released only when it survives the
gates that sit outside the model:

- No surviving citation, no answer. The refusal names the gap and who should fix it.
- The answer's own words have to be traceable to the passage it cites. A citation
  bolted onto a sentence whose words are not traceable to that source gets the
  answer refused.
- The excerpt under an answer is your document's text, never the model's. If the
  model invents a source or a paragraph reference, that citation is dropped before
  the answer is even scored.
- Certifications are never inferred. A roadmap is not a certificate.
- Two approved policies disagree? Both are quarantined until an owner reconciles.
- Expired pentest report? It cannot support a current claim, full stop.
- Legal commitments route to counsel before the model ever sees them.
- Nothing ships without a named human reviewer in a tamper-evident audit log.

The part I am proudest of: you do not have to take my word for any of this.
There is no demo call and no form gate. You sign up, upload evidence, and watch ten
questions get answered or refused, with citations, in about two minutes. The eval
suite with all the planted traps is public on GitHub.

One thing I want to be straight about, because this industry usually is not.

The free demo drafts on Google Gemini's free tier, and those terms let Google use
submitted content to improve their services. So the demo asks you for public
evidence: your published SOC 2 report, an ISO certificate, the policies already on
your trust center. It is a real run on real documents, just not on your secrets.

For confidential evidence there are two honest options. Bring your own key, and your
text goes to your provider account under your contract. Or take the managed tier,
which runs on a paid provider plan with a no-training commitment I will put in
writing. Sub-processors, in full: Google Gemini for drafting, Render for hosting.

I would rather lose a signup to that paragraph than win one by being vague about it.

Most tools answer confidently. This one refuses correctly.

Link in comments. I would love to hear how your team handles questionnaire season.

---

Comment 1 (posted immediately after): link to the live site.
Comment 2: link to the GitHub repo with the eval suite.

Hashtags (max 3, keep it quiet): #GRC #SecurityCompliance #B2BSaaS
