"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, ShieldAlert, Upload } from "lucide-react";
import { api, ITEM_STATES, type ItemState, type Questionnaire } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { STATE_LABEL } from "@/components/badges";
import { EmptyState, ErrorState, PageHeader } from "@/components/page-header";
import { CardsSkeleton } from "@/components/skeletons";
import { SummaryStrip, type SummaryStat } from "@/components/summary-strip";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/* Solid tones for the state bar; they match the StateBadge text colours. */
const BAR_TONE: Record<ItemState, string> = {
  RECEIVED: "bg-muted-foreground/60",
  NORMALISED: "bg-muted-foreground",
  MATCHED: "bg-status-info/70",
  DRAFTED: "bg-status-info",
  REVIEW: "bg-status-warn",
  APPROVED: "bg-status-ok/70",
  SENT: "bg-status-ok",
  HELD: "bg-status-warn/70",
  REFUSED: "bg-status-critical/70",
  QUARANTINED: "bg-status-critical",
};

const DAY = 86_400_000;

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function ageLabel(iso: string): string {
  const d = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / DAY));
  if (d === 0) return "today";
  if (d === 1) return "1 d ago";
  return `${d} d ago`;
}

function presentStates(q: Questionnaire): { state: ItemState; count: number }[] {
  return ITEM_STATES.flatMap((state) => {
    const count = q.counts[state] ?? 0;
    return count > 0 ? [{ state, count }] : [];
  });
}

function count(q: Questionnaire, s: ItemState): number {
  return q.counts[s] ?? 0;
}

function StateBar({ questionnaire }: { questionnaire: Questionnaire }) {
  const segments = presentStates(questionnaire);
  const total = segments.reduce((n, s) => n + s.count, 0) || 1;
  const summary = segments.map((s) => `${s.count} ${STATE_LABEL[s.state].toLowerCase()}`).join(", ");
  return (
    <div role="img" aria-label={`Item states: ${summary}`} className="flex h-1.5 w-full gap-px overflow-hidden rounded-[2px] bg-muted">
      {segments.map((s) => (
        <Tooltip key={s.state}>
          <TooltipTrigger
            render={
              <span
                className={cn("h-full min-w-1 transition-opacity hover:opacity-80", BAR_TONE[s.state])}
                style={{ flexBasis: `${(s.count / total) * 100}%` }}
              />
            }
          />
          <TooltipContent>
            <span className="tabular-nums">
              {s.count} of {questionnaire.total}
            </span>{" "}
            {STATE_LABEL[s.state].toLowerCase()}
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}

function QuestionnaireRow({ questionnaire: q }: { questionnaire: Questionnaire }) {
  const { href } = useEmbed();
  const sent = count(q, "SENT");
  const done = sent + count(q, "APPROVED");
  const needsHuman = count(q, "REVIEW") + count(q, "HELD") + count(q, "REFUSED");
  return (
    <li>
      <Link
        href={href(`/inbox/${q.id}`)}
        className="group grid grid-cols-1 items-center gap-x-6 gap-y-2 px-4 py-3 transition-colors hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_9rem_6.5rem_4.5rem]"
      >
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="truncate font-heading text-base leading-tight font-semibold">{q.customer}</h2>
            <span className="eyebrow shrink-0 rounded-sm border px-1 leading-4">{q.audience}</span>
          </div>
          <p className="mt-0.5 flex min-w-0 gap-2 font-mono text-[11px] text-muted-foreground">
            <span className="shrink-0">{q.deal_id}</span>
            <span aria-hidden className="opacity-50">/</span>
            <span className="truncate" title={q.filename}>
              {q.filename}
            </span>
          </p>
        </div>

        <div className="min-w-0">
          <StateBar questionnaire={q} />
          <p className="mt-1.5 flex gap-3 text-[11px] text-muted-foreground tabular-nums">
            <span>
              <span className="text-foreground">{done}</span>/{q.total} approved or sent
            </span>
            {needsHuman > 0 ? (
              <span>
                <span className="text-status-warn">{needsHuman}</span> need a human
              </span>
            ) : null}
          </p>
        </div>

        <div className="flex items-center lg:justify-start">
          {q.quarantined > 0 ? (
            <span className="inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border border-status-critical/40 bg-status-critical-wash px-1.5 font-mono text-[10px] uppercase tracking-wider text-status-critical">
              <ShieldAlert className="size-3" aria-hidden />
              {q.quarantined} quarantined
            </span>
          ) : (
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">clean intake</span>
          )}
        </div>

        <div className="text-xs tabular-nums">
          <span className="block text-foreground">{fmtDate(q.received_at)}</span>
          <span className="block text-[11px] text-muted-foreground">{ageLabel(q.received_at)}</span>
        </div>

        <span className="inline-flex items-center justify-end gap-1 text-xs font-medium text-muted-foreground group-hover:text-foreground">
          Open
          <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </span>
      </Link>
    </li>
  );
}

function inboxStats(data: Questionnaire[]): SummaryStat[] {
  const sum = (f: (q: Questionnaire) => number) => data.reduce((n, q) => n + f(q), 0);
  const open = sum((q) => q.total - count(q, "SENT") - count(q, "APPROVED"));
  const review = sum((q) => count(q, "REVIEW"));
  const held = sum((q) => count(q, "HELD"));
  const quarantined = sum((q) => q.quarantined);
  const weekAgo = Date.now() - 7 * DAY;
  const sentWeek = sum((q) => (new Date(q.received_at).getTime() >= weekAgo ? count(q, "SENT") : 0));
  return [
    { label: "Questionnaires", value: data.length, hint: `${sum((q) => q.total)} questions in total` },
    { label: "Questions open", value: open, hint: "not yet approved or sent" },
    { label: "In review", value: review, tone: review > 0 ? "warn" : "default", hint: "waiting on a reviewer" },
    { label: "Held", value: held, tone: held > 0 ? "warn" : "default", hint: "routed to an owner" },
    { label: "Quarantined", value: quarantined, tone: quarantined > 0 ? "critical" : "default", hint: "no model saw these" },
    { label: "Sent this week", value: sentWeek, tone: "ok", hint: "from intake in the last 7 d" },
  ];
}

export function Inbox() {
  const { data, error, loading } = useAsync(() => api.listQuestionnaires(), []);

  const sorted = React.useMemo(
    () => (data ? [...data].sort((a, b) => b.received_at.localeCompare(a.received_at)) : []),
    [data],
  );
  const stats = React.useMemo(() => (data ? inboxStats(data) : null), [data]);

  return (
    <div>
      <PageHeader
        eyebrow="Inbox"
        title="Questionnaires"
        description="Every questionnaire received, newest first. Open one to see its items and anything held in quarantine."
        actions={
          <Tooltip>
            <TooltipTrigger render={<span tabIndex={0} className="inline-flex rounded-lg" />}>
              <Button size="sm" variant="outline" disabled>
                <Upload aria-hidden />
                Upload questionnaire
              </Button>
            </TooltipTrigger>
            <TooltipContent>Upload goes live with the API</TooltipContent>
          </Tooltip>
        }
      />

      {loading && !data ? <CardsSkeleton count={3} /> : null}
      {error ? <ErrorState error={error} /> : null}

      {stats ? <SummaryStrip stats={stats} className="mb-4" /> : null}

      {data && sorted.length === 0 ? (
        <EmptyState title="Nothing received yet" body="Questionnaires appear here as soon as intake accepts them." />
      ) : null}

      {sorted.length > 0 ? (
        <section aria-label="Questionnaires" className="overflow-hidden rounded-md border bg-card text-card-foreground">
          <div
            aria-hidden
            className="hidden grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_9rem_6.5rem_4.5rem] gap-x-6 border-b bg-muted/40 px-4 py-1.5 lg:grid"
          >
            <span className="eyebrow">Customer and deal</span>
            <span className="eyebrow">Item states</span>
            <span className="eyebrow">Intake</span>
            <span className="eyebrow">Received</span>
            <span />
          </div>
          <ul className="divide-y">
            {sorted.map((q) => (
              <QuestionnaireRow key={q.id} questionnaire={q} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
