---
source_id: PLN-HUMAN-IN-LOOP
title: Human-in-the-Loop Design and Approval Plan
type: plan
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: human review, approval, governance, audit log, ai governance
---

A person signs, not the engine. Pramana establishes whether a statement is supported by an approved, in-force document. It does not take responsibility for making the statement. Every answer carries a status and every released answer can be routed to a named human for sign-off before it reaches a buyer.

Approval cannot manufacture evidence. The review interface only offers approval for an answer that already survived the gates. When nothing was released, a reviewer may either reject the question or author an answer themselves; an answer a human writes is recorded with status human_authored and is labelled as such in the answer contract and in the delivered workbook. A reader can always tell which answers the system supported and which a person asserted.

Review is part of the record. Every decision writes an event onto the same hash-chained audit log as the run it decided on, naming the reviewer, the action, the resulting status and the citations in force at that moment. Altering who approved something invalidates the chain from that point forward, and this is verified by test.

Approval of evidence is itself a human act. Documents ingested during onboarding are staged as unapproved and are refused by the citation gate. Promotion into the live corpus requires a named approver, which is recorded in a corpus log. Ingestion succeeding is never treated as a document being vouched for.

Operating modes. A run may be executed in manual review mode, in which the engine approves nothing and every drafted answer waits for a person. Demonstration runs use a labelled simulated reviewer that approves only gate-clean, complete-coverage drafts; every such event is recorded in the audit log as a simulated approval and is identified as such in the run report.
