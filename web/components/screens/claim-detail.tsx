"use client";

import Link from "next/link";
import { api, type ClaimStatus } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { ExceptionChip } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/page-header";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";

const STATUS_TONE: Record<ClaimStatus, string> = {
  verified: "text-status-ok",
  draft: "text-status-warn",
  deprecated: "text-muted-foreground",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "not recorded";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="eyebrow mb-1">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export function ClaimDetail({ id }: { id: string }) {
  const { href } = useEmbed();
  const { data: claim, error, loading } = useAsync(() => api.getClaim(id), [id]);

  return (
    <div>
      <ClaimsSubnav />
      <p className="mb-4 text-sm">
        <Link href={href("/claims")} className="text-muted-foreground hover:text-foreground hover:underline">
          Back to claims
        </Link>
      </p>

      {loading ? <LoadingState label="Loading claim" /> : null}
      {error ? <ErrorState error={error} /> : null}
      {!loading && !error && !claim ? <EmptyState title="Claim not found" /> : null}

      {claim ? (
        <article aria-labelledby="claim-statement">
          <p className="eyebrow mb-2">
            {claim.id} <span aria-hidden>/</span> <span className={STATUS_TONE[claim.status]}>{claim.status}</span>
          </p>
          <h1 id="claim-statement" className="font-heading max-w-[40ch] text-2xl leading-snug font-normal tracking-tight sm:text-3xl">
            {claim.statement}
          </h1>
          <p className="mt-3 max-w-[70ch] text-sm text-muted-foreground">{claim.scope}</p>

          <dl className="mt-8 grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Owner">
              <span>{claim.owner}</span>
              <br />
              <a href={`mailto:${claim.owner_email}`} className="font-mono text-xs text-muted-foreground hover:text-foreground hover:underline">
                {claim.owner_email}
              </a>
            </Field>
            <Field label="Status">
              <span className={cn("font-mono text-xs uppercase tracking-wider", STATUS_TONE[claim.status])}>{claim.status}</span>
            </Field>
            <Field label="Audience">
              <span className="font-mono text-xs uppercase tracking-wider">{claim.audience}</span>
            </Field>
            <Field label="Valid until">
              <span className="font-mono text-xs">{fmtDate(claim.valid_until)}</span>
            </Field>
            <Field label="Last verified">
              <span className="font-mono text-xs">{fmtDate(claim.last_verified)}</span>
            </Field>
            <Field label="Version">
              <code className="font-mono text-xs">{claim.version_hash}</code>
            </Field>
            <Field label="Approved answers">
              <span className="font-mono text-xs">{claim.approved_answers}</span>
            </Field>
          </dl>

          <section className="mt-8" aria-labelledby="claim-exceptions">
            <h2 id="claim-exceptions" className="eyebrow mb-2">
              Exceptions
            </h2>
            {claim.exceptions.length === 0 ? (
              <p className="text-sm text-muted-foreground">None. The statement applies without qualification.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {claim.exceptions.map((text) => (
                  <li key={text}>
                    <ExceptionChip text={text} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-8" aria-labelledby="claim-evidence">
            <h2 id="claim-evidence" className="eyebrow mb-2">
              Evidence
            </h2>
            {claim.evidence.length === 0 ? (
              <p className="text-sm text-muted-foreground">No evidence recorded.</p>
            ) : (
              <ul className="divide-y rounded-md border bg-card">
                {claim.evidence.map((e) => (
                  <li key={`${e.kind}:${e.ref}`} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-3 py-2">
                    <span className="min-w-0 break-all font-mono text-xs">
                      <span className="mr-2 uppercase tracking-wider text-muted-foreground">{e.kind.replaceAll("_", " ")}</span>
                      {e.ref}
                    </span>
                    <span className="text-xs text-muted-foreground">checked {fmtDate(e.checked_on)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </article>
      ) : null}
    </div>
  );
}
