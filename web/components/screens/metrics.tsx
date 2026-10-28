"use client";

import Link from "next/link";
import { api, DIFFICULTY_LABEL, type Difficulty } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { DetailSkeleton } from "@/components/skeletons";
import { PageHeader, ErrorState } from "@/components/page-header";
import { StatTile } from "@/components/stat-tile";
import { DifficultyBadge } from "@/components/badges";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

/** Review SLA per class, in days, from the plan. */
const SLA_DAYS: Record<Difficulty, number> = { reused: 1, covered: 2, parameter_missing: 3, novel: 5, contractual: 5 };
const CLASS_ORDER: Difficulty[] = ["reused", "covered", "parameter_missing", "novel", "contractual"];

export function Metrics() {
  const { data, loading, error } = useAsync(() => api.metrics());
  const { href } = useEmbed();
  if (loading) return <DetailSkeleton />;
  if (error) return <ErrorState error={error} />;
  if (!data) return null;
  const oldest = data.oldest_open_hard;

  return (
    <div>
      <PageHeader eyebrow="Metrics" title="What is still hard" description="Led by the oldest open hard question, never by the automation rate. Per class, so hard work cannot hide behind the easy." />

      <section className="mb-6 rounded-md border border-l-2 border-l-status-critical bg-card p-5" data-testid="oldest-open-hard">
        <p className="eyebrow mb-2">Oldest open hard question</p>
        {oldest ? (
          <>
            <p className="font-heading text-[30px] leading-[34px] font-semibold tracking-tight">{oldest.text}</p>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <span className="font-heading text-4xl font-semibold tabular-nums text-status-critical">{oldest.age_days} d</span>
              <span>open for {oldest.customer}</span>
              <DifficultyBadge difficulty={oldest.difficulty} />
              <Link href={href(`/review/${oldest.question_id}`)} className="text-primary underline-offset-2 hover:underline">
                Open in review
              </Link>
            </div>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No novel or contractual question is open.</p>
        )}
      </section>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Shipped wrong" value={String(data.shipped_wrong)} hint="Stop signal: rising stops the ladder" tone={data.shipped_wrong > 0 ? "critical" : "ok"} />
        <StatTile label="Human edit rate" value={`${Math.round(data.human_edit_rate * 100)}%`} hint="Of drafts a reviewer changed" tone={data.human_edit_rate > 0.25 ? "warn" : "default"} />
        <StatTile label="Claims fresh" value={`${Math.round(data.claim_fresh_share * 100)}%`} hint="Verified and not expired" tone={data.claim_fresh_share < 0.8 ? "warn" : "ok"} />
        <StatTile label="Novel per month" value={String(data.novel_per_month)} hint="Each becomes a claim or a refusal" />
        <StatTile label="Follow-ups" value={data.follow_ups_per_questionnaire.toFixed(1)} hint="Per questionnaire" />
        <StatTile label="p95 per question" value={`${(data.p95_latency_ms / 1000).toFixed(1)} s`} hint="Target 8 s" tone={data.p95_latency_ms > 8000 ? "warn" : "default"} />
        <StatTile label="Cost per 100" value={`$${data.cost_per_100_usd.toFixed(2)}`} hint="Target $1 on Haiku" />
      </div>

      <section className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Class</TableHead>
              <TableHead className="text-right">Open</TableHead>
              <TableHead className="text-right">Sent</TableHead>
              <TableHead className="text-right">Median to sign-off</TableHead>
              <TableHead className="text-right">Review SLA</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {CLASS_ORDER.map((c) => {
              const row = data.by_class[c];
              const breach = row.median_hours > SLA_DAYS[c] * 24;
              return (
                <TableRow key={c}>
                  <TableCell>
                    <DifficultyBadge difficulty={c} />
                    <span className="sr-only">{DIFFICULTY_LABEL[c]}</span>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{row.open}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.sent}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", breach && "text-status-critical")}>{row.median_hours} h</TableCell>
                  <TableCell className="text-right text-muted-foreground">{SLA_DAYS[c]} d</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
