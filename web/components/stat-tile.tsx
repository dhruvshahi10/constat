import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";

/**
 * Stat tile composed from shadcn Card. 21st.dev's MIT stat cards were
 * checked first (konsstepnov, redrob-labs); they ship only through an
 * API-key install with no readable source, so the tile is composed here.
 */
export function StatTile({ label, value, hint, tone = "default", className }: { label: string; value: string; hint?: string; tone?: "default" | "ok" | "warn" | "critical" | "info"; className?: string }) {
  const toneClass = {
    default: "text-foreground",
    ok: "text-status-ok",
    warn: "text-status-warn",
    critical: "text-status-critical",
    info: "text-primary",
  }[tone];
  return (
    <Card className={cn("gap-1 rounded-md px-4 py-3", className)}>
      <p className="eyebrow">{label}</p>
      <p className={cn("font-heading text-3xl font-light leading-none tabular-nums", toneClass)}>{value}</p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </Card>
  );
}
