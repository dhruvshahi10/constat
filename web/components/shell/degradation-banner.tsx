"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { api, type DegradationState } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { cn } from "@/lib/utils";

/**
 * Plain words about what is flowing and what is held while the reviewer is
 * away. The slot stays empty in the normal state so the top bar is calm.
 */
export function DegradationBanner({ className, compact }: { className?: string; compact?: boolean }) {
  const { data } = useAsync(() => api.degradation());
  if (!data || data.state !== "degraded") return null;
  return <DegradationNotice state={data} className={className} compact={compact} />;
}

export function DegradationNotice({ state, className, compact }: { state: DegradationState; className?: string; compact?: boolean }) {
  const sentence = `${state.reviewer} has been away ${state.reviewer_idle_hours} h. ${state.flowing} approved and unchanged ${state.flowing === 1 ? "answer continues" : "answers continue"}; ${state.held} novel or changed ${state.held === 1 ? "answer is" : "answers are"} held${state.backup ? `, deal blockers go to ${state.backup}` : ""}.`;
  return (
    <Link
      href="/ops/degradation"
      className={cn(
        "flex min-w-0 items-center gap-2 rounded-md border border-status-warn/40 bg-status-warn-wash px-2.5 py-1 text-xs text-foreground hover:border-status-warn",
        className,
      )}
      data-testid="degradation-banner"
      role="status"
    >
      <span aria-hidden className="relative flex size-2 shrink-0"><span className="absolute inline-flex size-full animate-ping rounded-full bg-status-warn opacity-60 motion-reduce:animate-none" /><span className="relative inline-flex size-2 rounded-full bg-status-warn" /></span>
      <AlertTriangle className="size-3.5 shrink-0 text-status-warn" aria-hidden />
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-status-warn">Degraded</span>
      <span className={cn("min-w-0 line-clamp-2 sm:truncate", compact && "hidden sm:inline")}>{sentence}</span>
    </Link>
  );
}
