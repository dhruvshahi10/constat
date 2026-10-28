"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { api, type ItemState, type QuestionItem, type Questionnaire } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { DifficultyBadge, StateBadge } from "@/components/badges";
import { EmptyState, ErrorState } from "@/components/page-header";
import { DetailSkeleton, TableSkeleton } from "@/components/skeletons";
import { SummaryStrip, type SummaryStat } from "@/components/summary-strip";
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const HEAD = "sticky top-0 z-10 h-8 bg-card px-3 text-[11px] font-medium text-muted-foreground shadow-[inset_0_-1px_0_var(--border)]";
const CELL = "h-9 px-3 py-0";

function ItemRow({ item, showGaps }: { item: QuestionItem; showGaps?: boolean }) {
  const router = useRouter();
  const { href } = useEmbed();
  const target = href(`/review/${item.id}`);
  const quarantined = item.state === "QUARANTINED";
  const gaps = showGaps ? (item.verdict?.gaps ?? []) : [];
  const route = item.route ?? item.verdict?.route ?? null;

  return (
    <TableRow
      tabIndex={0}
      onClick={() => router.push(target)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          router.push(target);
        }
      }}
      className="cursor-pointer focus-visible:bg-muted/50 focus-visible:outline-none"
    >
      <TableCell
        className={cn(CELL, "w-10 font-mono text-xs text-muted-foreground tabular-nums", quarantined && "shadow-[inset_2px_0_0_var(--status-critical)]")}
      >
        {item.ordinal}
      </TableCell>
      <TableCell className={cn(CELL, "w-full max-w-0")}>
        <div className="flex min-w-0 items-center gap-2">
          <Link href={target} className="min-w-0 truncate text-foreground hover:underline" tabIndex={-1} title={item.text}>
            {item.text}
          </Link>
          {item.blocks_deal ? (
            <span className="shrink-0 rounded-sm bg-status-critical-wash px-1 font-mono text-[9.5px] uppercase tracking-wider text-status-critical">
              blocks deal
            </span>
          ) : null}
        </div>
        {quarantined && !gaps.length ? (
          <p className="truncate pb-1 text-[11px] leading-4 text-status-critical">Quarantined before any model saw it.</p>
        ) : null}
        {gaps.length ? (
          <p className="truncate pb-1 text-[11px] leading-4 text-muted-foreground" title={gaps.join(" ")}>
            {gaps.join(" ")}
          </p>
        ) : null}
      </TableCell>
      <TableCell className={cn(CELL, "max-w-[9rem]")}>
        <span className="block truncate text-xs text-muted-foreground" title={item.domain}>
          {item.domain}
        </span>
      </TableCell>
      <TableCell className={CELL}>
        <StateBadge state={item.state} />
      </TableCell>
      <TableCell className={CELL}>
        <DifficultyBadge difficulty={item.difficulty} />
      </TableCell>
      <TableCell className={cn(CELL, "font-mono text-[11px]")}>
        {item.claim_id ? (
          <span className="text-foreground/90">{item.claim_id}</span>
        ) : (
          <span className="text-muted-foreground/60">none</span>
        )}
      </TableCell>
      <TableCell className={cn(CELL, "max-w-[11rem]")}>
        <span className="block truncate font-mono text-[11px] text-muted-foreground" title={route ?? undefined}>
          {route ?? "none"}
        </span>
      </TableCell>
      <TableCell className={cn(CELL, "text-right font-mono text-[11px] text-muted-foreground tabular-nums")}>{item.age_days} d</TableCell>
    </TableRow>
  );
}

function ItemsTable({ items, showGaps, emptyTitle, emptyBody }: { items: QuestionItem[]; showGaps?: boolean; emptyTitle: string; emptyBody: string }) {
  if (items.length === 0) return <EmptyState title={emptyTitle} body={emptyBody} />;
  return (
    <div className="max-h-[70vh] overflow-auto rounded-md border bg-card">
      <table data-slot="table" className="w-full min-w-[860px] text-[13px] tabular-nums">
        <TableHeader className="[&_tr]:border-b-0">
          <TableRow className="hover:bg-transparent">
            <TableHead scope="col" className={cn(HEAD, "w-10")}>#</TableHead>
            <TableHead scope="col" className={HEAD}>Question</TableHead>
            <TableHead scope="col" className={HEAD}>Domain</TableHead>
            <TableHead scope="col" className={HEAD}>State</TableHead>
            <TableHead scope="col" className={HEAD}>Difficulty</TableHead>
            <TableHead scope="col" className={HEAD}>Claim</TableHead>
            <TableHead scope="col" className={HEAD}>Route</TableHead>
            <TableHead scope="col" className={cn(HEAD, "text-right")}>Age</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <ItemRow key={item.id} item={item} showGaps={showGaps} />
          ))}
        </TableBody>
      </table>
    </div>
  );
}

function itemStats(q: Questionnaire, items: QuestionItem[] | null): SummaryStat[] {
  const by = (s: ItemState) => (items ? items.filter((i) => i.state === s).length : (q.counts[s] ?? 0));
  const review = by("REVIEW");
  const held = by("HELD");
  const refused = by("REFUSED");
  const sent = by("SENT");
  const blocking = items ? items.filter((i) => i.blocks_deal && i.state !== "SENT").length : null;
  return [
    { label: "Items", value: q.total, hint: blocking ? `${blocking} block the deal` : "in this questionnaire" },
    { label: "In review", value: review, tone: review ? "warn" : "default", hint: "waiting on a reviewer" },
    { label: "Held", value: held, tone: held ? "warn" : "default", hint: "routed to an owner" },
    { label: "Refused", value: refused, tone: refused ? "critical" : "default", hint: "no claim covers them" },
    { label: "Quarantined", value: q.quarantined, tone: q.quarantined ? "critical" : "default", hint: "held at intake" },
    { label: "Sent", value: sent, tone: "ok", hint: `${Math.round((sent / (q.total || 1)) * 100)}% complete` },
  ];
}

export function QuestionnaireItems({ id }: { id: string }) {
  const { href } = useEmbed();
  const header = useAsync(() => api.getQuestionnaire(id), [id]);
  const items = useAsync(() => api.listItems(id), [id]);
  const quarantine = useAsync(() => api.listQuarantine(id), [id]);

  const sortedItems = React.useMemo(
    () => (items.data ? [...items.data].sort((a, b) => a.ordinal - b.ordinal) : []),
    [items.data],
  );
  const quarantineCount = quarantine.data?.length ?? header.data?.quarantined ?? 0;

  if (header.loading && !header.data) return <DetailSkeleton />;
  if (header.error) return <ErrorState error={header.error} />;
  const q = header.data;
  if (!q) return <EmptyState title="Questionnaire not found" />;

  return (
    <div>
      <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
        <Link href={href("/inbox")} className="hover:text-foreground hover:underline">
          Inbox
        </Link>
        <span aria-hidden>/</span>
        <span className="text-foreground" aria-current="page">
          {q.customer}
        </span>
      </nav>

      <header className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow mb-1.5">
            {q.deal_id} <span aria-hidden>/</span> {q.audience}
          </p>
          <h1 className="font-heading text-[30px] leading-[34px] font-semibold tracking-tight">{q.customer}</h1>
          <p className="mt-1.5 flex flex-wrap gap-x-3 text-sm text-muted-foreground">
            <span className="font-mono text-xs leading-5">{q.filename}</span>
            <span>received {fmtDate(q.received_at)}</span>
          </p>
        </div>
        {q.quarantined > 0 ? (
          <span className="inline-flex h-6 items-center gap-1 rounded-sm border border-status-critical/40 bg-status-critical-wash px-2 font-mono text-[11px] uppercase tracking-wider text-status-critical">
            <ShieldAlert className="size-3.5" aria-hidden />
            {q.quarantined} quarantined
          </span>
        ) : null}
      </header>

      <SummaryStrip stats={itemStats(q, items.data)} className="mb-4" />

      <Tabs defaultValue="items">
        <TabsList aria-label="Questionnaire views">
          <TabsTrigger value="items">
            Items
            <span className="font-mono text-[11px] text-muted-foreground tabular-nums">{q.total}</span>
          </TabsTrigger>
          <TabsTrigger value="quarantine">
            Quarantine
            {quarantineCount > 0 ? (
              <span className="font-mono text-[11px] text-status-critical tabular-nums" aria-label={`${quarantineCount} quarantined`}>
                {quarantineCount}
              </span>
            ) : null}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="items" className="mt-3">
          {items.loading && !items.data ? <TableSkeleton rows={8} /> : null}
          {items.error ? <ErrorState error={items.error} /> : null}
          {items.data ? (
            <ItemsTable
              items={sortedItems}
              emptyTitle="No items"
              emptyBody="The normaliser has not produced any items for this questionnaire yet."
            />
          ) : null}
        </TabsContent>

        <TabsContent value="quarantine" className="mt-3">
          <p className="mb-3 text-[13px] text-muted-foreground">
            Items here were held at intake because the text addressed the system rather than the vendor. No model saw them.
          </p>
          {quarantine.loading && !quarantine.data ? <TableSkeleton rows={2} /> : null}
          {quarantine.error ? <ErrorState error={quarantine.error} /> : null}
          {quarantine.data ? (
            <ItemsTable
              items={quarantine.data}
              showGaps
              emptyTitle="Nothing in quarantine"
              emptyBody="Every item in this questionnaire passed intake."
            />
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}
