"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { Claim, QuestionItem, Verdict } from "@/lib/api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";

/**
 * The chain under every answer, horizontal and compact: question, claim,
 * evidence, test. Where the chain breaks, the rail says so in words.
 */
export function ProvenanceRail({ item, verdict, claims, className }: { item: QuestionItem; verdict: Verdict; claims: Claim[]; className?: string }) {
  const { href } = useEmbed();
  const claim = claims[0] ?? null;
  const evidence = claim?.evidence.filter((e) => e.kind !== "vanta_test") ?? [];
  const tests = claim?.evidence.filter((e) => e.kind === "vanta_test") ?? [];

  const stop = (label: string, title: string, body: string, tone: "ok" | "warn" | "critical" | "muted", link?: string) => {
    const toneCls = {
      ok: "border-status-ok/40 bg-status-ok-wash",
      warn: "border-status-warn/40 bg-status-warn-wash",
      critical: "border-status-critical/40 bg-status-critical-wash",
      muted: "border-border bg-muted",
    }[tone];
    const inner = (
      <>
        <span className="eyebrow block">{label}</span>
        <span className="block truncate text-xs font-medium">{title}</span>
        <span className="block truncate text-[11px] text-muted-foreground">{body}</span>
      </>
    );
    return link ? (
      <Link href={link} className={cn("block min-w-0 flex-1 rounded-md border px-2.5 py-1.5 hover:brightness-95", toneCls)}>
        {inner}
      </Link>
    ) : (
      <div className={cn("min-w-0 flex-1 rounded-md border px-2.5 py-1.5", toneCls)}>{inner}</div>
    );
  };

  const arrow = <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />;

  return (
    <nav aria-label="Provenance" className={cn("flex items-stretch gap-1.5 overflow-x-auto", className)} data-testid="provenance-rail">
      {stop("question", `${item.customer} Q${item.ordinal}`, item.domain, "muted", href(`/questions/${item.id}/provenance`))}
      {arrow}
      {claim
        ? stop("claim", claim.owner, `${claim.id} @ ${claim.version_hash}, until ${claim.valid_until}`, claim.status === "verified" ? "ok" : "warn", href(`/claims/${claim.id}`))
        : stop("claim", "No covering claim", verdict.route ? `routed to ${verdict.route}` : "nobody owns this yet", "critical")}
      {arrow}
      {evidence.length
        ? stop("evidence", evidence[0].ref, evidence.length > 1 ? `and ${evidence.length - 1} more` : (evidence[0].checked_on ? `checked ${evidence[0].checked_on}` : "unchecked"), "ok")
        : stop("evidence", "None attached", "a claim without evidence is a sentence", claim ? "warn" : "muted")}
      {arrow}
      {tests.length
        ? stop("test", tests[0].ref.replace(/^vanta:test:/, ""), tests[0].checked_on ? `passing on ${tests[0].checked_on}` : "status unknown", "ok")
        : stop("test", "No continuous test", "freshness relies on the owner", claim ? "warn" : "muted")}
    </nav>
  );
}
