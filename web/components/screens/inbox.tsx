"use client";

import * as React from "react";
import Link from "next/link";
import { api, ITEM_STATES, type ItemState, type Questionnaire } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { StateBadge, STATE_LABEL } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page-header";

/* Solid tones for the state bar; they match the StateBadge text colours. */
const BAR_TONE: Record<ItemState, string> = {
  RECEIVED: "bg-muted-foreground",
  NORMALISED: "bg-muted-foreground",
  MATCHED: "bg-status-info",
  DRAFTED: "bg-status-info",
  REVIEW: "bg-status-warn",
  APPROVED: "bg-status-ok",
  SENT: "bg-status-ok",
  HELD: "bg-status-warn",
  REFUSED: "bg-status-critical",
  QUARANTINED: "bg-status-critical",
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function presentStates(q: Questionnaire): { state: ItemState; count: number }[] {
  return ITEM_STATES.flatMap((state) => {
    const count = q.counts[state] ?? 0;
    return count > 0 ? [{ state, count }] : [];
  });
}

function StateBar({ questionnaire }: { questionnaire: Questionnaire }) {
  const segments = presentStates(questionnaire);
  const total = segments.reduce((n, s) => n + s.count, 0) || 1;
  const summary = segments.map((s) => `${s.count} ${STATE_LABEL[s.state].toLowerCase()}`).join(", ");
  return (
    <div
      role="img"
      aria-label={`Item states: ${summary}`}
      className="flex h-1.5 w-full gap-px overflow-hidden rounded-sm bg-muted"
    >
      {segments.map((s) => (
        <span
          key={s.state}
          className={cn("h-full", BAR_TONE[s.state])}
          style={{ flexBasis: `${(s.count / total) * 100}%` }}
        />
      ))}
    </div>
  );
}

function QuestionnaireCard({ questionnaire: q }: { questionnaire: Questionnaire }) {
  const { href } = useEmbed();
  const segments = presentStates(q);
  return (
    <li>
      <Link
        href={href(`/inbox/${q.id}`)}
        className="block rounded-md border bg-card p-4 text-card-foreground transition-colors hover:bg-muted/40 focus-visible:bg-muted/40"
      >
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            <h2 className="font-heading text-lg leading-tight">{q.customer}</h2>
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground">
              <span>{q.deal_id}</span>
              <span className="break-all">{q.filename}</span>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {q.quarantined > 0 ? (
              <span className="inline-flex h-6 items-center rounded-sm border border-status-critical/40 bg-status-critical-wash px-2 font-mono text-[11px] uppercase tracking-wider text-status-critical">
                {q.quarantined} quarantined
              </span>
            ) : null}
            <span className="eyebrow">{q.audience}</span>
          </div>
        </div>

        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
          <div className="flex gap-1.5">
            <dt>Received</dt>
            <dd className="text-foreground">{fmtDate(q.received_at)}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt>Items</dt>
            <dd className="text-foreground">{q.total}</dd>
          </div>
        </dl>

        <div className="mt-3">
          <StateBar questionnaire={q} />
        </div>

        <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Items by state">
          {segments.map((s) => (
            <li key={s.state} className="flex items-center gap-1">
              <StateBadge state={s.state} />
              <span className="font-mono text-[11px] text-muted-foreground">{s.count}</span>
            </li>
          ))}
        </ul>
      </Link>
    </li>
  );
}

export function Inbox() {
  const { data, error, loading } = useAsync(() => api.listQuestionnaires(), []);

  const sorted = React.useMemo(
    () => (data ? [...data].sort((a, b) => b.received_at.localeCompare(a.received_at)) : []),
    [data],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Inbox"
        title="Questionnaires"
        description="Every questionnaire received, newest first. Open one to see its items and anything held in quarantine."
      />
      {loading ? <LoadingState label="Loading questionnaires" /> : null}
      {error ? <ErrorState error={error} /> : null}
      {!loading && !error && sorted.length === 0 ? (
        <EmptyState title="Nothing received yet" body="Questionnaires appear here as soon as intake accepts them." />
      ) : null}
      {sorted.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {sorted.map((q) => (
            <QuestionnaireCard key={q.id} questionnaire={q} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
