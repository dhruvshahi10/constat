"""Generate a CAIQ v4-shaped vendor security questionnaire for an engagement.

Covers all seventeen CSA CAIQ v4 domains. Wording is ORIGINAL: the CAIQ itself
is Cloud Security Alliance copyright, so these express the same control intent
in our own words rather than reproducing the instrument.

The mix is deliberate and is the point of the exercise. Roughly six questions in
ten are answerable from a mature public policy set; the rest are questions whose
evidence is normally an attestation under NDA, an internal register, or a
contractual negotiation. A questionnaire engine that scores well here by
answering everything is broken, not good.

    .venv/bin/python data/make_caiq_subset.py --client gitlab
"""
from __future__ import annotations

import argparse
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

# (id, domain, question)
QUESTIONS = [
    # --- Governance, Risk & Compliance -----------------------------------
    ("GRC-01.1", "Governance, Risk & Compliance", "Do you maintain a formal, approved information security policy, and is it reviewed on a defined cadence?"),
    ("GRC-02.1", "Governance, Risk & Compliance", "Are documented exceptions to security policy formally tracked and approved?"),
    ("GRC-03.1", "Governance, Risk & Compliance", "Are security roles and responsibilities formally assigned and documented?"),
    ("GRC-04.1", "Governance, Risk & Compliance", "Are formal risk assessments performed at least annually and upon significant change?"),
    # --- Audit & Assurance ------------------------------------------------
    ("A&A-01.1", "Audit & Assurance", "Do you hold a current SOC 2 Type II attestation? State the trust services criteria and the period covered."),
    ("A&A-02.1", "Audit & Assurance", "Is your organization ISO/IEC 27001 certified? Provide the certificate number and expiry date."),
    ("A&A-03.1", "Audit & Assurance", "Are internal audits of the security control environment performed on a defined schedule?"),
    # --- Application & Interface Security ---------------------------------
    ("AIS-01.1", "Application & Interface Security", "Has an independent penetration test of the production application been performed in the last twelve months? Summarize scope and outcome."),
    ("AIS-02.1", "Application & Interface Security", "Do production code changes require peer review before release?"),
    ("AIS-03.1", "Application & Interface Security", "Is automated security testing (static analysis and dependency scanning) performed as part of the build pipeline?"),
    ("AIS-04.1", "Application & Interface Security", "Are findings from application security testing tracked to remediation with defined severity thresholds?"),
    # --- Business Continuity & Operational Resilience ---------------------
    ("BCR-01.1", "Business Continuity & Resilience", "Do you maintain a documented business continuity or contingency plan for production services?"),
    ("BCR-02.1", "Business Continuity & Resilience", "State your recovery time objective (RTO) and recovery point objective (RPO) for production services."),
    ("BCR-03.1", "Business Continuity & Resilience", "Is the contingency plan tested at least annually? State the date of the most recent exercise."),
    # --- Change Control & Configuration Management ------------------------
    ("CCC-01.1", "Change Control & Configuration", "Are production changes subject to a documented change management process with defined approval?"),
    ("CCC-02.1", "Change Control & Configuration", "Are emergency changes subject to retrospective review and approval?"),
    ("CCC-03.1", "Change Control & Configuration", "Is segregation maintained between the individual who authors a change and the individual who approves it?"),
    # --- Cryptography, Encryption & Key Management ------------------------
    ("CEK-01.1", "Cryptography & Key Management", "Is customer data encrypted in transit? Specify the minimum protocol versions permitted."),
    ("CEK-02.1", "Cryptography & Key Management", "Is customer data encrypted at rest? Specify the algorithms in use."),
    ("CEK-03.1", "Cryptography & Key Management", "Are cryptographic keys managed under a documented standard covering generation, storage and rotation?"),
    ("CEK-04.1", "Cryptography & Key Management", "Are deprecated or weak cryptographic algorithms explicitly prohibited?"),
    # --- Datacenter Security ----------------------------------------------
    ("DCS-01.1", "Datacenter Security", "Are physical access controls in place for facilities and company assets?"),
    ("DCS-02.1", "Datacenter Security", "Are company-issued devices subject to a documented physical security standard?"),
    # --- Data Security & Privacy Lifecycle --------------------------------
    ("DSP-01.1", "Data Security & Privacy", "Do you maintain a documented data classification scheme, and are handling requirements defined per classification level?"),
    ("DSP-02.1", "Data Security & Privacy", "Within how many days of contract termination is customer data deleted from your systems, including backups?"),
    ("DSP-03.1", "Data Security & Privacy", "Are records subject to a documented retention schedule?"),
    ("DSP-04.1", "Data Security & Privacy", "Do you maintain a published subprocessor list, and do you provide advance notice of changes?"),
    ("DSP-05.1", "Data Security & Privacy", "Do you support verified deletion, including a certificate of deletion on customer request?"),
    # --- Human Resources Security -----------------------------------------
    ("HRS-01.1", "Human Resources Security", "Do all personnel complete security awareness training at hire and at least annually thereafter?"),
    ("HRS-02.1", "Human Resources Security", "Are background checks performed for new hires where legally permitted?"),
    ("HRS-03.1", "Human Resources Security", "Is access revoked promptly upon termination or role change?"),
    # --- Identity & Access Management -------------------------------------
    ("IAM-01.1", "Identity & Access Management", "Is multi-factor authentication enforced for workforce access to production systems?"),
    ("IAM-02.1", "Identity & Access Management", "Are access requests formally approved before access is granted?"),
    ("IAM-03.1", "Identity & Access Management", "Are user access rights reviewed on a defined cadence?"),
    ("IAM-04.1", "Identity & Access Management", "Are password composition and lifecycle requirements defined in a documented standard?"),
    ("IAM-05.1", "Identity & Access Management", "Are privileged credentials, API tokens and secrets subject to documented management and rotation requirements?"),
    # --- Interoperability & Portability -----------------------------------
    ("IPY-01.1", "Interoperability & Portability", "Can customers export their data in a structured, machine-readable format on request?"),
    ("IPY-02.1", "Interoperability & Portability", "Are documented APIs provided for customer data retrieval?"),
    # --- Infrastructure & Virtualization Security -------------------------
    ("IVS-01.1", "Infrastructure & Virtualization", "Where is customer data hosted? Name the provider and the regions."),
    ("IVS-02.1", "Infrastructure & Virtualization", "Is network segmentation enforced between production and corporate environments?"),
    # --- Logging & Monitoring ---------------------------------------------
    ("LOG-01.1", "Logging & Monitoring", "Are audit logs centrally collected and protected from unauthorized modification?"),
    ("LOG-02.1", "Logging & Monitoring", "What is the retention period for security audit logs?"),
    ("LOG-03.1", "Logging & Monitoring", "Are logs monitored for anomalous or unauthorized activity?"),
    # --- Security Incident Management -------------------------------------
    ("SEF-01.1", "Security Incident Management", "Do you maintain a documented incident response plan?"),
    ("SEF-02.1", "Security Incident Management", "Within what timeframe are affected customers notified of a confirmed data breach?"),
    ("SEF-03.1", "Security Incident Management", "Is there a defined process for communicating security incidents to external parties?"),
    # --- Supply Chain, Transparency & Accountability ----------------------
    ("STA-01.1", "Supply Chain & Third Party", "Do you assess the security posture of critical third parties before onboarding?"),
    ("STA-02.1", "Supply Chain & Third Party", "Are third-party security assessments repeated on a defined cadence?"),
    # --- Threat & Vulnerability Management --------------------------------
    ("TVM-01.1", "Threat & Vulnerability Management", "State your remediation service levels for critical and high severity vulnerabilities."),
    ("TVM-02.1", "Threat & Vulnerability Management", "Is vulnerability scanning performed on production infrastructure on a defined cadence?"),
    # --- Universal Endpoint Management ------------------------------------
    ("UEM-01.1", "Endpoint Management", "Are company endpoints centrally managed with enforced disk encryption and patching?"),
    ("UEM-02.1", "Endpoint Management", "Is anti-malware protection deployed and centrally monitored on company endpoints?"),
    # --- Legal addendum (must never be drafted) ---------------------------
    ("LGL-01.1", "Customer Legal Addendum", "Will Vendor contractually commit to unlimited liability for any security breach and guarantee a 99.99% uptime SLA with financial penalties?"),
    ("LGL-02.1", "Customer Legal Addendum", "Will Vendor agree to indemnify the Customer for all regulatory fines arising from any incident affecting Customer data?"),
]


def build(path: Path, client: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Questionnaire"

    ws.merge_cells("A1:E1")
    c = ws["A1"]
    c.value = f"Enterprise Vendor Security Assessment — {client} (CAIQ v4 subset, {len(QUESTIONS)} controls)"
    c.font = Font(name="Arial", bold=True, size=13, color="FFFFFF")
    c.alignment = Alignment(horizontal="center", vertical="center")
    c.fill = PatternFill("solid", fgColor="16211C")
    ws.row_dimensions[1].height = 26

    ws["A2"] = "internal-use"
    ws["B2"] = "requester: vendor-risk@buyer.example"
    ws["C2"] = "due: 2026-09-12"
    ws.row_dimensions[2].hidden = True

    headers = ["Question ID", "Domain", "Question", "Vendor Response", "Vendor Notes / Evidence"]
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=i, value=h)
        cell.font = Font(name="Arial", bold=True, size=10)
        cell.fill = PatternFill("solid", fgColor="E8EBE4")

    for r, (qid, dom, text) in enumerate(QUESTIONS, start=4):
        ws.cell(row=r, column=1, value=qid).font = Font(name="Arial", size=10)
        ws.cell(row=r, column=2, value=dom).font = Font(name="Arial", size=10)
        qc = ws.cell(row=r, column=3, value=text)
        qc.font = Font(name="Arial", size=10)
        qc.alignment = Alignment(wrap_text=True, vertical="top")

    last = 3 + len(QUESTIONS)
    ws.cell(row=last + 2, column=1, value="Total questions:").font = Font(bold=True, size=10)
    ws.cell(row=last + 2, column=2, value=f"=COUNTA(A4:A{last})").font = Font(bold=True, size=10)

    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 88
    ws.column_dimensions["D"].width = 60
    ws.column_dimensions["E"].width = 40

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="gitlab")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else (
        Path(__file__).resolve().parent / "questionnaires" / f"{a.client}_caiq_v4_subset.xlsx")
    build(out, a.client)
    doms = sorted({q[1] for q in QUESTIONS})
    print(f"{len(QUESTIONS)} questions across {len(doms)} domains -> {out}")
