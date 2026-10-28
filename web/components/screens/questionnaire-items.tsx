"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type QuestionItem } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { DifficultyBadge, StateBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function ItemRow({ item, showGaps }: { item: QuestionItem; showGaps?: boolean }) {
  const router = useRouter();
  const { href } = useEmbed();
  const target = href(`/review/${item.id}`);
  const quarantined = item.state === "QUARANTINED";
  const gaps = showGaps ? (item.verdict?.gaps ?? []) : [];

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
        className={cn("w-12 align-top font-mono text-xs text-muted-foreground", quarantined && "border-l-2 border-l-status-critical")}
      >
        {item.ordinal}
      </TableCell>
      <TableCell className="w-40 align-top whitespace-normal text-xs text-muted-foreground">{item.domain}</TableCell>
      <TableCell className="min-w-[18rem] align-top whitespace-normal">
        <Link href={target} className="line-clamp-2 text-foreground hover:underline" tabIndex={-1}>
          {item.text}
        </Link>
        {quarantined ? (
          <p className="mt-1 text-xs text-status-critical">Quarantined before any model saw it.</p>
        ) : null}
        {gaps.length ? (
          <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
            {gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        ) : null}
      </TableCell>
      <TableCell className="align-top">
        <StateBadge state={item.state} />
      </TableCell>
      <TableCell className="align-top">
        <DifficultyBadge difficulty={item.difficulty} />
      </TableCell>
      <TableCell className="align-top font-mono text-[11px] text-muted-foreground">
        {item.claim_id ?? <span className="opacity-60">none</span>}
      </TableCell>
    </TableRow>
  );
}

function ItemsTable({ items, showGaps, emptyTitle, emptyBody }: { items: QuestionItem[]; showGaps?: boolean; emptyTitle: string; emptyBody: string }) {
  if (items.length === 0) return <EmptyState title={emptyTitle} body={emptyBody} />;
  return (
    <div className="rounded-md border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className="w-12">#</TableHead>
            <TableHead scope="col">Domain</TableHead>
            <TableHead scope="col">Question</TableHead>
            <TableHead scope="col">State</TableHead>
            <TableHead scope="col">Difficulty</TableHead>
            <TableHead scope="col">Claim</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <ItemRow key={item.id} item={item} showGaps={showGaps} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
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

  if (header.loading) return <LoadingState label="Loading questionnaire" />;
  if (header.error) return <ErrorState error={header.error} />;
  const q = header.data;
  if (!q) return <EmptyState title="Questionnaire not found" />;

  return (
    <div>
      <p className="mb-4 text-sm">
        <Link href={href("/inbox")} className="text-muted-foreground hover:text-foreground hover:underline">
          Back to inbox
        </Link>
      </p>
      <PageHeader
        eyebrow={`${q.deal_id} / ${q.audience}`}
        title={q.customer}
        description={`${q.filename}, received ${fmtDate(q.received_at)}. ${q.total} items.`}
        actions={
          q.quarantined > 0 ? (
            <span className="inline-flex h-6 items-center rounded-sm border border-status-critical/40 bg-status-critical-wash px-2 font-mono text-[11px] uppercase tracking-wider text-status-critical">
              {q.quarantined} quarantined
            </span>
          ) : null
        }
      />

      <Tabs defaultValue="items">
        <TabsList aria-label="Questionnaire views">
          <TabsTrigger value="items">Items</TabsTrigger>
          <TabsTrigger value="quarantine">
            Quarantine
            {quarantineCount > 0 ? (
              <span className="font-mono text-[11px] text-status-critical" aria-label={`${quarantineCount} quarantined`}>
                {quarantineCount}
              </span>
            ) : null}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="items" className="mt-4">
          {items.loading ? <LoadingState label="Loading items" /> : null}
          {items.error ? <ErrorState error={items.error} /> : null}
          {items.data ? (
            <ItemsTable
              items={sortedItems}
              emptyTitle="No items"
              emptyBody="The normaliser has not produced any items for this questionnaire yet."
            />
          ) : null}
        </TabsContent>

        <TabsContent value="quarantine" className="mt-4">
          <p className="mb-3 text-sm text-muted-foreground">
            Items here were held at intake because the text addressed the system rather than the vendor. No model saw them.
          </p>
          {quarantine.loading ? <LoadingState label="Loading quarantine" /> : null}
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
