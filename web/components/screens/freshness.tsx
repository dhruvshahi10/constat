"use client";

import * as React from "react";
import Link from "next/link";
import { api, type FreshnessClaim, type FreshnessGroup } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, PageHeader } from "@/components/page-header";
import { CardsSkeleton } from "@/components/skeletons";
import { SummaryStrip } from "@/components/summary-strip";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";

/** The timeline runs from today to 180 days out; ticks mark the 30 and 90 day lines. */
const SCALE = 180;
const TICKS = [30, 90] as const;

const ROW_GRID = "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,1fr)_minmax(10rem,16rem)_6.5rem_7rem]";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function tone(days: number): "critical" | "warn" | "info" | "ok" {
  if (days < 0) return "critical";
  if (days < 30) return "warn";
  if (days < 90) return "info";
  return "ok";
}

const FILL: Record<ReturnType<typeof tone>, string> = {
  critical: "bg-status-critical",
  warn: "bg-status-warn",
  info: "bg-status-info",
  ok: "bg-status-ok",
};

const TEXT: Record<ReturnType<typeof tone>, string> = {
  critical: "text-status-critical",
  warn: "text-status-warn",
  info: "text-foreground",
  ok: "text-muted-foreground",
};

function Timeline({ days }: { days: number }) {
  const t = tone(days);
  const pct = Math.min(100, (Math.max(0, days) / SCALE) * 100);
  const label = days < 0 ? `Expired ${-days} days ago` : `${days} days left on a ${SCALE} day scale`;
  return (
    <div role="img" aria-label={label} className="relative h-1.5 w-full rounded-[2px] bg-muted">
      {TICKS.map((d) => (
        <span key={d} aria-hidden className="absolute -top-0.5 h-2.5 w-px bg-border" style={{ left: `${(d / SCALE) * 100}%` }} />
      ))}
      {days < 0 ? (
        <span aria-hidden className="absolute -top-0.5 left-0 h-2.5 w-1 rounded-[1px] bg-status-critical" />
      ) : (
        <span aria-hidden className={cn("absolute inset-y-0 left-0 rounded-[2px]", FILL[t])} style={{ width: `${Math.max(pct, 1.5)}%` }} />
      )}
    </div>
  );
}

function ClaimRow({ claim }: { claim: FreshnessClaim }) {
  const { href } = useEmbed();
  const t = tone(claim.days_left);
  return (
    <li className={cn(ROW_GRID, "min-h-9 px-3 py-1.5 transition-colors hover:bg-muted/40")}>
      <Link href={href(`/claims/${claim.id}`)} className="min-w-0 truncate text-[13px] hover:underline" title={claim.statement}>
        {claim.status === "draft" ? (
          <span className="mr-1.5 rounded-sm bg-status-warn-wash px-1 font-mono text-[9.5px] uppercase tracking-wider text-status-warn">draft</span>
        ) : null}
        {claim.statement}
      </Link>
      <div className="col-span-2 sm:col-span-1">
        <Timeline days={claim.days_left} />
      </div>
      <span className="hidden font-mono text-[11px] text-muted-foreground tabular-nums sm:block">{fmtDate(claim.valid_until)}</span>
      <span className={cn("col-start-2 row-start-1 text-right font-mono text-[11px] tabular-nums sm:col-start-auto sm:row-start-auto", TEXT[t])}>
        {claim.days_left < 0 ? `expired ${-claim.days_left} d` : `${claim.days_left} d left`}
      </span>
    </li>
  );
}

function OwnerSection({ group: g }: { group: FreshnessGroup }) {
  const expired = g.claims.filter((c) => c.days_left < 0).length;
  const soon = g.claims.filter((c) => c.days_left >= 0 && c.days_left < 30).length;
  const headingId = `owner-${g.owner_email.replace(/[^a-z0-9]/gi, "-")}`;
  return (
    <section aria-labelledby={headingId} className="overflow-hidden rounded-md border bg-card">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b bg-muted/40 px-3 py-2">
        <h2 id={headingId} className="font-heading text-base leading-tight font-semibold">
          {g.owner}
        </h2>
        <a href={`mailto:${g.owner_email}`} className="font-mono text-[11px] text-muted-foreground hover:text-foreground hover:underline">
          {g.owner_email}
        </a>
        <span className="ml-auto flex gap-3 font-mono text-[11px] tabular-nums">
          <span className="text-muted-foreground">{g.claims.length} claims</span>
          {expired ? <span className="text-status-critical">{expired} expired</span> : null}
          {soon ? <span className="text-status-warn">{soon} under 30 d</span> : null}
        </span>
      </header>
      <ul className="divide-y">
        {g.claims.map((c) => (
          <ClaimRow key={c.id} claim={c} />
        ))}
      </ul>
    </section>
  );
}

export function Freshness() {
  const { data, error, loading } = useAsync(() => api.freshness(), []);

  const summary = React.useMemo(() => {
    const all = data?.flatMap((g) => g.claims) ?? [];
    return {
      expired: all.filter((c) => c.days_left < 0).length,
      under30: all.filter((c) => c.days_left >= 0 && c.days_left < 30).length,
      under90: all.filter((c) => c.days_left >= 0 && c.days_left < 90).length,
      total: all.length,
      owners: data?.length ?? 0,
      ownersOverdue: data?.filter((g) => g.claims.some((c) => c.days_left < 0)).length ?? 0,
    };
  }, [data]);

  // Owners with the most urgent claim first.
  const groups = React.useMemo(
    () =>
      data
        ? [...data].sort((a, b) => Math.min(...a.claims.map((c) => c.days_left)) - Math.min(...b.claims.map((c) => c.days_left)))
        : [],
    [data],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Freshness"
        description="Who must re-verify what, soonest first. An expired claim stops supporting answers until its owner renews it."
      />
      <ClaimsSubnav />

      {loading && !data ? <CardsSkeleton count={4} /> : null}
      {error ? <ErrorState error={error} /> : null}

      {data ? (
        <>
          <SummaryStrip
            className="mb-4 sm:grid-cols-4 md:grid-cols-4"
            stats={[
              { label: "Expired", value: summary.expired, tone: summary.expired ? "critical" : "default", hint: "no longer supporting answers" },
              { label: "Under 30 d", value: summary.under30, tone: summary.under30 ? "warn" : "default", hint: "re-verify this month" },
              { label: "Under 90 d", value: summary.under90, tone: summary.under90 ? "info" : "default", hint: `of ${summary.total} claims` },
              { label: "Owners", value: summary.owners, hint: summary.ownersOverdue ? `${summary.ownersOverdue} with an expired claim` : "all in date" },
            ]}
          />

          {groups.length === 0 ? (
            <EmptyState title="No claims to track" />
          ) : (
            <>
              <div aria-hidden className={cn(ROW_GRID, "mb-1 hidden px-3 sm:grid")}>
                <span className="eyebrow">Claim</span>
                <span className="relative block h-4 font-mono text-[10px] text-muted-foreground tabular-nums">
                  <span className="absolute left-0">0</span>
                  {TICKS.map((d) => (
                    <span key={d} className="absolute -translate-x-1/2" style={{ left: `${(d / SCALE) * 100}%` }}>
                      {d}
                    </span>
                  ))}
                  <span className="absolute right-0">{SCALE} d</span>
                </span>
                <span className="eyebrow">Valid until</span>
                <span className="eyebrow text-right">Left</span>
              </div>
              <div className="flex flex-col gap-3">
                {groups.map((g) => (
                  <OwnerSection key={g.owner_email} group={g} />
                ))}
              </div>
            </>
          )}
        </>
      ) : null}
    </div>
  );
}
