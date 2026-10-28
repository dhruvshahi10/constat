"use client";

import Link from "next/link";
import { Progress as ProgressPrimitive } from "@base-ui/react/progress";
import { api, type Claim, type ClaimStatus, type EvidenceKind } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { ExceptionChip } from "@/components/badges";
import { EmptyState, ErrorState } from "@/components/page-header";
import { DetailSkeleton } from "@/components/skeletons";
import { SummaryStrip, type SummaryStat } from "@/components/summary-strip";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";
import { ProgressIndicator, ProgressTrack } from "@/components/ui/progress";

const STATUS_TONE: Record<ClaimStatus, string> = {
  verified: "text-status-ok",
  draft: "text-status-warn",
  deprecated: "text-muted-foreground",
};

const EVIDENCE_LABEL: Record<EvidenceKind, string> = {
  vanta_test: "Vanta test",
  policy: "Policy",
  standard: "Standard",
  report: "Report",
  certificate: "Certificate",
  attestation: "Attestation",
  config: "Config",
  statement: "Statement",
};

const DAY = 86_400_000;

function fmtDate(iso: string | null): string {
  if (!iso) return "not recorded";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function validity(claim: Claim) {
  const start = new Date(claim.last_verified).getTime();
  const end = new Date(claim.valid_until).getTime();
  const now = Date.now();
  const span = Math.max(DAY, end - start);
  const elapsed = Math.min(100, Math.max(0, ((now - start) / span) * 100));
  const daysLeft = Math.round((end - now) / DAY);
  const tone = daysLeft < 0 ? "critical" : daysLeft < 30 ? "warn" : "ok";
  return { elapsed, daysLeft, tone, spanDays: Math.round(span / DAY) } as const;
}

function RailRow({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-3 px-3 py-2", className)}>
      <dt className="eyebrow">{label}</dt>
      <dd className="min-w-0 text-[13px]">{children}</dd>
    </div>
  );
}

function ValidityBar({ claim }: { claim: Claim }) {
  const v = validity(claim);
  const indicator = { critical: "bg-status-critical", warn: "bg-status-warn", ok: "bg-status-ok" }[v.tone];
  const text = { critical: "text-status-critical", warn: "text-status-warn", ok: "text-status-ok" }[v.tone];
  return (
    <div className="space-y-1.5">
      <ProgressPrimitive.Root value={Math.round(v.elapsed)} aria-label="Share of the validity window elapsed">
        <ProgressTrack className="h-1.5 rounded-[2px]">
          <ProgressIndicator className={indicator} />
        </ProgressTrack>
      </ProgressPrimitive.Root>
      <div className="flex justify-between font-mono text-[10.5px] text-muted-foreground tabular-nums">
        <span>{fmtDate(claim.last_verified)}</span>
        <span>{fmtDate(claim.valid_until)}</span>
      </div>
      <p className={cn("font-mono text-[11px] tabular-nums", text)}>
        {v.daysLeft < 0 ? `Expired ${-v.daysLeft} d ago` : `${v.daysLeft} d left`}
        <span className="text-muted-foreground"> of a {v.spanDays} d window</span>
      </p>
    </div>
  );
}

function detailStats(claim: Claim): SummaryStat[] {
  const v = validity(claim);
  return [
    {
      label: v.daysLeft < 0 ? "Expired" : "Valid for",
      value: v.daysLeft < 0 ? `${-v.daysLeft} d` : `${v.daysLeft} d`,
      tone: v.tone,
      hint: v.daysLeft < 0 ? "answers citing it are held" : `until ${fmtDate(claim.valid_until)}`,
    },
    { label: "Exceptions", value: claim.exceptions.length, tone: claim.exceptions.length ? "warn" : "default", hint: "travel into every answer" },
    { label: "Evidence", value: claim.evidence.length, hint: claim.evidence.length ? "items on record" : "none recorded" },
    { label: "Approved answers", value: claim.approved_answers, tone: "info", hint: "rest on this claim" },
  ];
}

export function ClaimDetail({ id }: { id: string }) {
  const { href } = useEmbed();
  const { data: claim, error, loading } = useAsync(() => api.getClaim(id), [id]);

  return (
    <div>
      <ClaimsSubnav />
      <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
        <Link href={href("/claims")} className="hover:text-foreground hover:underline">
          Claims
        </Link>
        <span aria-hidden>/</span>
        <span className="text-foreground" aria-current="page">
          {id}
        </span>
      </nav>

      {loading && !claim ? <DetailSkeleton /> : null}
      {error ? <ErrorState error={error} /> : null}
      {!loading && !error && !claim ? <EmptyState title="Claim not found" /> : null}

      {claim ? (
        <article aria-labelledby="claim-statement">
          <header className="mb-4">
            <p className="eyebrow mb-2 flex flex-wrap items-center gap-2">
              <span className="normal-case">{claim.id}</span>
              <span aria-hidden>/</span>
              <span className={STATUS_TONE[claim.status]}>{claim.status}</span>
              <span aria-hidden>/</span>
              <span>{claim.audience}</span>
            </p>
            <h1 id="claim-statement" className="max-w-[48ch] font-heading text-2xl leading-snug font-normal tracking-tight sm:text-[28px] sm:leading-[36px]">
              {claim.statement}
            </h1>
          </header>

          <SummaryStrip stats={detailStats(claim)} className="mb-5 sm:grid-cols-4 md:grid-cols-4" />

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
            <div className="min-w-0 space-y-5">
              <section aria-labelledby="claim-scope" className="rounded-md border bg-card">
                <h2 id="claim-scope" className="eyebrow border-b px-3 py-2">
                  Scope
                </h2>
                <p className="px-3 py-2.5 text-sm leading-relaxed">{claim.scope}</p>
              </section>

              <section aria-labelledby="claim-exceptions" className="rounded-md border bg-card">
                <div className="flex items-center justify-between border-b px-3 py-2">
                  <h2 id="claim-exceptions" className="eyebrow">
                    Exceptions
                  </h2>
                  <span className={cn("font-mono text-[11px] tabular-nums", claim.exceptions.length ? "text-status-warn" : "text-muted-foreground")}>
                    {claim.exceptions.length}
                  </span>
                </div>
                <div className="px-3 py-2.5">
                  {claim.exceptions.length === 0 ? (
                    <p className="text-sm text-muted-foreground">None. The statement applies without qualification.</p>
                  ) : (
                    <>
                      <ul className="flex flex-col gap-2">
                        {claim.exceptions.map((text) => (
                          <li key={text}>
                            <ExceptionChip text={text} />
                          </li>
                        ))}
                      </ul>
                      <p className="mt-2.5 text-xs text-muted-foreground">
                        The gate refuses any answer that cites this claim and drops an exception.
                      </p>
                    </>
                  )}
                </div>
              </section>
            </div>

            <aside aria-label="Claim metadata" className="space-y-4 lg:sticky lg:top-16">
              <dl className="divide-y rounded-md border bg-card">
                <RailRow label="Owner">
                  <span className="block truncate">{claim.owner}</span>
                  <a
                    href={`mailto:${claim.owner_email}`}
                    className="block truncate font-mono text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                  >
                    {claim.owner_email}
                  </a>
                </RailRow>
                <RailRow label="Status">
                  <span className={cn("font-mono text-[11px] uppercase tracking-wider", STATUS_TONE[claim.status])}>{claim.status}</span>
                </RailRow>
                <RailRow label="Audience">
                  <span className="font-mono text-[11px] uppercase tracking-wider">{claim.audience}</span>
                </RailRow>
                <div className="space-y-2 px-3 py-2.5">
                  <dt className="eyebrow">Validity</dt>
                  <dd>
                    <ValidityBar claim={claim} />
                  </dd>
                </div>
                <RailRow label="Version">
                  <code className="font-mono text-[11px]">{claim.version_hash}</code>
                </RailRow>
                <RailRow label="Answers">
                  <span className="font-mono text-[11px] tabular-nums">{claim.approved_answers} approved</span>
                </RailRow>
              </dl>

              <section aria-labelledby="claim-evidence" className="rounded-md border bg-card">
                <div className="flex items-center justify-between border-b px-3 py-2">
                  <h2 id="claim-evidence" className="eyebrow">
                    Evidence
                  </h2>
                  <span className="font-mono text-[11px] text-muted-foreground tabular-nums">{claim.evidence.length}</span>
                </div>
                {claim.evidence.length === 0 ? (
                  <p className="px-3 py-2.5 text-sm text-muted-foreground">No evidence recorded.</p>
                ) : (
                  <ul className="divide-y">
                    {claim.evidence.map((e) => (
                      <li key={`${e.kind}:${e.ref}`} className="px-3 py-2">
                        <p className="flex items-center justify-between gap-2">
                          <span className="eyebrow">{EVIDENCE_LABEL[e.kind]}</span>
                          <span className="font-mono text-[10.5px] text-muted-foreground tabular-nums">
                            {e.checked_on ? `checked ${fmtDate(e.checked_on)}` : "never checked"}
                          </span>
                        </p>
                        <p className="mt-0.5 truncate font-mono text-[11.5px]" title={e.ref}>
                          {e.ref}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>
        </article>
      ) : null}
    </div>
  );
}
