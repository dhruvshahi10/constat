"use client";

import * as React from "react";
import Link from "next/link";
import { api, type FreshnessClaim } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page-header";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function DaysLeftChip({ days }: { days: number }) {
  const expired = days < 0;
  const soon = !expired && days < 30;
  const label = expired ? `expired ${-days} d ago` : `${days} d left`;
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center rounded-sm px-1.5 font-mono text-[10px] uppercase tracking-[0.12em] whitespace-nowrap",
        expired && "bg-status-critical-wash text-status-critical",
        soon && "bg-status-warn-wash text-status-warn",
        !expired && !soon && "bg-status-ok-wash text-status-ok",
      )}
    >
      {label}
    </span>
  );
}

function ClaimRow({ claim }: { claim: FreshnessClaim }) {
  const { href } = useEmbed();
  return (
    <li className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 px-3 py-2.5">
      <Link href={href(`/claims/${claim.id}`)} className="min-w-0 flex-1 basis-[16rem] text-sm leading-snug hover:underline">
        {claim.statement}
      </Link>
      <span className="flex shrink-0 items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground">{fmtDate(claim.valid_until)}</span>
        <DaysLeftChip days={claim.days_left} />
      </span>
    </li>
  );
}

export function Freshness() {
  const { data, error, loading } = useAsync(() => api.freshness(), []);

  const summary = React.useMemo(() => {
    const all = data?.flatMap((g) => g.claims) ?? [];
    return {
      expired: all.filter((c) => c.days_left < 0).length,
      soon: all.filter((c) => c.days_left >= 0 && c.days_left < 30).length,
      total: all.length,
    };
  }, [data]);

  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Freshness"
        description="Who must re-verify what, soonest first. An expired claim stops supporting answers until its owner renews it."
      />
      <ClaimsSubnav />

      {loading ? <LoadingState label="Loading freshness" /> : null}
      {error ? <ErrorState error={error} /> : null}

      {data ? (
        <>
          <p className="mb-6 text-sm" aria-live="polite">
            <span className={cn("font-mono", summary.expired > 0 ? "text-status-critical" : "text-muted-foreground")}>
              {summary.expired} expired
            </span>
            <span className="text-muted-foreground">, </span>
            <span className={cn("font-mono", summary.soon > 0 ? "text-status-warn" : "text-muted-foreground")}>
              {summary.soon} expiring within 30 days
            </span>
            <span className="text-muted-foreground">, of {summary.total} claims.</span>
          </p>

          {data.length === 0 ? (
            <EmptyState title="No claims to track" />
          ) : (
            <div className="flex flex-col gap-6">
              {data.map((g) => (
                <section key={g.owner_email} aria-labelledby={`owner-${g.owner_email}`}>
                  <h2 id={`owner-${g.owner_email}`} className="font-heading text-lg leading-tight">
                    {g.owner}
                  </h2>
                  <p className="mb-2 font-mono text-xs text-muted-foreground">{g.owner_email}</p>
                  <ul className="divide-y rounded-md border bg-card">
                    {g.claims.map((c) => (
                      <ClaimRow key={c.id} claim={c} />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
