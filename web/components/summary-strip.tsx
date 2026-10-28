import Link from "next/link";
import { cn } from "@/lib/utils";

export interface SummaryStat {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "ok" | "warn" | "critical" | "info";
  href?: string;
}

const TONE: Record<NonNullable<SummaryStat["tone"]>, string> = {
  default: "text-foreground",
  ok: "text-status-ok",
  warn: "text-status-warn",
  critical: "text-status-critical",
  info: "text-primary",
};

/** A single row of numbers above a working surface. Dense by design. */
export function SummaryStrip({ stats, className }: { stats: SummaryStat[]; className?: string }) {
  return (
    <div className={cn("grid grid-cols-2 divide-x divide-y rounded-md border bg-card sm:grid-cols-3 md:grid-cols-6 md:divide-y-0", className)} role="list">
      {stats.map((s) => {
        const body = (
          <>
            <p className="eyebrow truncate">{s.label}</p>
            <p className={cn("mt-0.5 font-heading text-2xl font-semibold leading-none tabular-nums", TONE[s.tone ?? "default"])}>{s.value}</p>
            {s.hint ? <p className="mt-1 truncate text-[11px] text-muted-foreground">{s.hint}</p> : null}
          </>
        );
        const cls = "block min-w-0 px-3 py-2.5";
        return (
          <div key={s.label} role="listitem" className="min-w-0">
            {s.href ? (
              <Link href={s.href} className={cn(cls, "hover:bg-muted/60")}>
                {body}
              </Link>
            ) : (
              <div className={cls}>{body}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
