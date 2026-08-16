"""The fixed 10-question hosted demo set.

Chosen so that any company's real documents exercise the full trap taxonomy:
straightforward citable facts, a certification claim (cert-evidence-class
gate), a staleness-prone claim, a deletion-window question (contradiction
bait), a hosting question (the retrieval showcase), and a legal commitment
(pre-draft routing). IDs are stable: they key the review queue and evals.
"""

DEMO_QUESTIONS: list[tuple[str, str, str]] = [
    ("H-01", "Cryptography", "Is customer data encrypted in transit? Specify minimum protocol versions."),
    ("H-02", "Cryptography", "Is customer data encrypted at rest? Specify algorithms and key management approach."),
    ("H-03", "Identity & Access", "Is multi-factor authentication enforced for all workforce access to production systems?"),
    ("H-04", "Incident Management", "Do you have a documented incident response plan, and within what timeframe are customers notified of a confirmed breach?"),
    ("H-05", "Data Security & Privacy", "Within how many days of contract termination is customer data deleted from your systems, including backups?"),
    ("H-06", "Data Security & Privacy", "Do you maintain a published subprocessor list with advance notice of changes?"),
    ("H-07", "Infrastructure", "Where is customer data hosted (provider and regions)?"),
    ("H-08", "Application Security", "Has an independent penetration test been performed in the last 12 months? Summarize scope and outcome."),
    ("H-09", "Audit & Assurance", "Is your organization ISO/IEC 27001 certified? Provide certificate number and expiry."),
    ("H-10", "Customer Legal Addendum", "Will Vendor contractually commit to unlimited liability for any security breach with financial penalties?"),
]
