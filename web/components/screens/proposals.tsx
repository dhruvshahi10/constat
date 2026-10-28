"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Check, X } from "lucide-react";
import { api, type ClaimProposal } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, PageHeader } from "@/components/page-header";
import { CardsSkeleton } from "@/components/skeletons";
import { SummaryStrip } from "@/components/summary-strip";
import { WordDiff } from "@/components/word-diff";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";
import { Button } from "@/components/ui/button";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const STATUS_TONE: Record<ClaimProposal["status"], string> = {
  pending: "text-status-warn bg-status-warn-wash",
  approved: "text-status-ok bg-status-ok-wash",
  rejected: "text-muted-foreground bg-muted",
};

const STATUS_RAIL: Record<ClaimProposal["status"], string> = {
  pending: "shadow-[inset_2px_0_0_var(--status-warn)]",
  approved: "shadow-[inset_2px_0_0_var(--status-ok)]",
  rejected: "",
};

type Filter = "all" | ClaimProposal["status"];

const chip = "inline-flex h-5 items-center rounded-sm px-1.5 font-mono text-[10px] uppercase tracking-[0.12em] whitespace-nowrap";

function ProposalCard({ proposal: p, onDone }: { proposal: ClaimProposal; onDone: () => void }) {
  const { href } = useEmbed();
  const [busy, setBusy] = React.useState<"approve" | "reject" | null>(null);

  async function act(kind: "approve" | "reject") {
    setBusy(kind);
    try {
      if (kind === "approve") {
        await api.approveProposal(p.id);
        toast.success("Proposal approved");
      } else {
        await api.rejectProposal(p.id);
        toast.success("Proposal rejected");
      }
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "The store refused the change");
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className={cn("rounded-md border bg-card text-card-foreground", STATUS_RAIL[p.status])}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b px-3 py-2">
        <span className={cn(chip, "bg-muted text-muted-foreground")}>{p.kind === "new" ? "new claim" : "change"}</span>
        <span className={cn(chip, STATUS_TONE[p.status])}>{p.status}</span>
        <span className="font-mono text-[11px] text-muted-foreground">{p.id}</span>
        {p.claim_id ? (
          <Link href={href(`/claims/${p.claim_id}`)} className="font-mono text-[11px] text-primary hover:underline">
            {p.claim_id}
          </Link>
        ) : null}
        <span className="ml-auto text-[11px] text-muted-foreground">
          <span className="font-mono text-foreground">{p.proposed_by}</span>
          <span className="tabular-nums"> on {fmtDate(p.proposed_at)}</span>
        </span>
      </div>

      <div className="grid gap-3 px-3 py-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <div className="min-w-0 space-y-1.5">
          <p className="eyebrow">Reason</p>
          <p className="text-[13px] leading-snug">{p.reason}</p>
          {p.source_question_id ? (
            <p className="text-xs">
              <Link href={href(`/review/${p.source_question_id}`)} className="font-mono text-[11px] text-primary underline-offset-2 hover:underline">
                Source {p.source_question_id}
              </Link>
            </p>
          ) : (
            <p className="font-mono text-[11px] text-muted-foreground">No source question</p>
          )}
        </div>

        <div className="min-w-0 rounded-md border bg-background/40 p-2.5">
          {p.kind === "change" && p.previous_statement ? (
            <WordDiff before={p.previous_statement} after={p.statement} />
          ) : (
            <>
              <p className="eyebrow mb-1">Proposed statement</p>
              <p className="text-sm leading-snug">{p.statement}</p>
            </>
          )}
        </div>
      </div>

      {p.status === "pending" ? (
        <div className="flex flex-wrap items-center justify-end gap-2 border-t px-3 py-2">
          <p className="mr-auto text-[11px] text-muted-foreground">A second person must approve; the proposer cannot.</p>
          <Button size="sm" variant="outline" onClick={() => act("reject")} disabled={busy !== null} aria-label={`Reject proposal ${p.id}`}>
            <X aria-hidden />
            {busy === "reject" ? "Rejecting" : "Reject"}
          </Button>
          <Button size="sm" onClick={() => act("approve")} disabled={busy !== null} aria-label={`Approve proposal ${p.id}`}>
            <Check aria-hidden />
            {busy === "approve" ? "Approving" : "Approve"}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

export function Proposals() {
  const { data, error, loading, reload } = useAsync(() => api.listProposals(), []);
  const [filter, setFilter] = React.useState<Filter>("all");

  const sorted = React.useMemo(() => {
    if (!data) return [];
    const rank = { pending: 0, approved: 1, rejected: 2 } as const;
    return [...data].sort((a, b) => rank[a.status] - rank[b.status] || b.proposed_at.localeCompare(a.proposed_at));
  }, [data]);

  const counts = React.useMemo(() => {
    const c = { pending: 0, approved: 0, rejected: 0 };
    for (const p of data ?? []) c[p.status] += 1;
    return c;
  }, [data]);

  const visible = filter === "all" ? sorted : sorted.filter((p) => p.status === filter);
  const filters: { id: Filter; label: string; n: number }[] = [
    { id: "all", label: "All", n: data?.length ?? 0 },
    { id: "pending", label: "Pending", n: counts.pending },
    { id: "approved", label: "Approved", n: counts.approved },
    { id: "rejected", label: "Rejected", n: counts.rejected },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Proposals"
        description="Edits and new claims waiting for a second person. The proposer can never approve their own proposal; the store enforces the second-person rule."
      />
      <ClaimsSubnav />

      {loading && !data ? <CardsSkeleton count={3} /> : null}
      {error ? <ErrorState error={error} /> : null}

      {data ? (
        <>
          <SummaryStrip
            className="mb-4 sm:grid-cols-3 md:grid-cols-3"
            stats={[
              { label: "Pending", value: counts.pending, tone: counts.pending ? "warn" : "default", hint: "waiting on a second person" },
              { label: "Approved", value: counts.approved, tone: "ok", hint: "now live in the claim store" },
              { label: "Rejected", value: counts.rejected, hint: "closed without change" },
            ]}
          />

          <div role="group" aria-label="Show proposals" className="mb-3 inline-flex rounded-md border bg-card p-0.5">
            {filters.map((f) => (
              <button
                key={f.id}
                type="button"
                aria-pressed={filter === f.id}
                onClick={() => setFilter(f.id)}
                className={cn(
                  "inline-flex h-6 items-center gap-1.5 rounded-[3px] px-2 text-xs transition-colors",
                  filter === f.id ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {f.label}
                <span className="font-mono text-[10.5px] tabular-nums">{f.n}</span>
              </button>
            ))}
          </div>

          {visible.length === 0 ? (
            <EmptyState
              title={filter === "all" ? "No proposals" : `No ${filter} proposals`}
              body="Reviewer edits that touch a claim, and imported answers, appear here for approval."
            />
          ) : (
            <ul className="flex flex-col gap-2.5">
              {visible.map((p) => (
                <ProposalCard key={p.id} proposal={p} onDone={reload} />
              ))}
            </ul>
          )}
        </>
      ) : null}
    </div>
  );
}
