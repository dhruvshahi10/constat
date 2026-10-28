"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { api, type ClaimProposal } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page-header";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";
import { Button } from "@/components/ui/button";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const STATUS_TONE: Record<ClaimProposal["status"], string> = {
  pending: "text-status-warn",
  approved: "text-status-ok",
  rejected: "text-muted-foreground",
};

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
    <li className="rounded-md border bg-card p-4 text-card-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-5 items-center rounded-sm bg-muted px-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          {p.kind === "new" ? "new claim" : "change"}
        </span>
        <span className={cn("font-mono text-[10px] uppercase tracking-[0.12em]", STATUS_TONE[p.status])}>{p.status}</span>
        {p.claim_id ? (
          <Link href={href(`/claims/${p.claim_id}`)} className="font-mono text-[11px] text-muted-foreground hover:text-foreground hover:underline">
            {p.claim_id}
          </Link>
        ) : null}
      </div>

      <p className="mt-2 text-xs text-muted-foreground">
        Proposed by <span className="font-mono text-foreground">{p.proposed_by}</span> on {fmtDate(p.proposed_at)}
      </p>
      <p className="mt-2 text-sm">{p.reason}</p>
      {p.source_question_id ? (
        <p className="mt-1 text-xs">
          <Link href={href(`/review/${p.source_question_id}`)} className="text-primary underline-offset-2 hover:underline">
            Source question {p.source_question_id}
          </Link>
        </p>
      ) : null}

      {p.kind === "change" ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-dashed p-3">
            <p className="eyebrow mb-1">Before</p>
            <p className="text-sm leading-snug text-muted-foreground">{p.previous_statement ?? "No previous statement"}</p>
          </div>
          <div className="rounded-md border p-3">
            <p className="eyebrow mb-1">After</p>
            <p className="text-sm leading-snug">{p.statement}</p>
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-md border p-3">
          <p className="eyebrow mb-1">Proposed statement</p>
          <p className="text-sm leading-snug">{p.statement}</p>
        </div>
      )}

      {p.status === "pending" ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => act("approve")} disabled={busy !== null} aria-label={`Approve proposal ${p.id}`}>
            {busy === "approve" ? "Approving" : "Approve"}
          </Button>
          <Button size="sm" variant="outline" onClick={() => act("reject")} disabled={busy !== null} aria-label={`Reject proposal ${p.id}`}>
            {busy === "reject" ? "Rejecting" : "Reject"}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

export function Proposals() {
  const { data, error, loading, reload } = useAsync(() => api.listProposals(), []);

  const sorted = React.useMemo(() => {
    if (!data) return [];
    const rank = { pending: 0, approved: 1, rejected: 2 } as const;
    return [...data].sort((a, b) => rank[a.status] - rank[b.status] || b.proposed_at.localeCompare(a.proposed_at));
  }, [data]);

  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Proposals"
        description="Edits and new claims waiting for a second person. The proposer can never approve their own proposal; the store enforces the second-person rule."
      />
      <ClaimsSubnav />

      {loading && !data ? <LoadingState label="Loading proposals" /> : null}
      {error ? <ErrorState error={error} /> : null}
      {data && sorted.length === 0 ? (
        <EmptyState title="No proposals" body="Reviewer edits that touch a claim will appear here for approval." />
      ) : null}
      {sorted.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {sorted.map((p) => (
            <ProposalCard key={p.id} proposal={p} onDone={reload} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
