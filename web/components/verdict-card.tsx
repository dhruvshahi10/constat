import Link from "next/link";
import { ShieldCheck, ShieldAlert, ShieldX } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Confidence, Verdict } from "@/lib/api";
import { DifficultyBadge, FlagChip } from "@/components/badges";

const HEAD = {
  ANSWER: { icon: ShieldCheck, label: "Answer", sub: "A verified claim covers this. It may leave after review.", tone: "text-status-ok", edge: "border-l-status-ok", wash: "bg-status-ok-wash" },
  HOLD_HUMAN: { icon: ShieldAlert, label: "Hold for a human", sub: "The gate will not decide this alone.", tone: "text-status-warn", edge: "border-l-status-warn", wash: "bg-status-warn-wash" },
  REFUSE: { icon: ShieldX, label: "Refuse", sub: "Nothing here is allowed to leave.", tone: "text-status-critical", edge: "border-l-status-critical", wash: "bg-status-critical-wash" },
} as const;

/**
 * The gate's decision, rendered the same way everywhere: the Ask bar, the
 * command palette, the question page and the embedded views.
 */
export function VerdictCard({ verdict, question, className, compact }: { verdict: Verdict; question?: string; className?: string; compact?: boolean }) {
  const h = HEAD[verdict.outcome];
  const Icon = h.icon;
  return (
    <section
      className={cn("overflow-hidden rounded-md border border-l-[3px] bg-card text-card-foreground", h.edge, className)}
      aria-label={`Verdict: ${verdict.outcome}`}
      data-testid="verdict-card"
      data-outcome={verdict.outcome}
    >
      <header className={cn("flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2.5", h.wash)}>
        <Icon className={cn("shrink-0", compact ? "size-4" : "size-5", h.tone)} aria-hidden />
        <span className={cn("font-heading font-semibold", compact ? "text-sm" : "text-base", h.tone)}>{h.label}</span>
        <span className="font-mono text-[10px] tracking-[0.14em] uppercase opacity-70">{verdict.outcome.replace("_", " ")}</span>
        <DifficultyBadge difficulty={verdict.difficulty} className="ml-auto" />
        {verdict.outcome === "ANSWER" && verdict.confidence ? <ConfidencePill confidence={verdict.confidence} /> : null}
        {verdict.reused ? <span className="eyebrow">verbatim reuse</span> : null}
      </header>

      <div className="space-y-3 px-4 py-3">
        {question ? <p className="text-sm text-muted-foreground">{question}</p> : null}
        {!compact ? <p className="text-xs text-muted-foreground">{h.sub}</p> : null}

        {verdict.outcome === "ANSWER" && verdict.answer ? <p className="text-sm leading-relaxed">{verdict.answer}</p> : null}

        {verdict.outcome === "ANSWER" && verdict.confidence ? (
          <details className="group text-xs text-muted-foreground" data-testid="confidence-basis">
            <summary className="cursor-pointer select-none font-mono tracking-wider uppercase hover:text-foreground">
              Why {verdict.confidence.band} confidence
            </summary>
            <ul className="mt-1.5 space-y-0.5 pl-1">
              {verdict.confidence.basis.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </details>
        ) : null}

        {verdict.gaps.length ? (
          <ul className="space-y-1 text-sm">
            {verdict.gaps.map((g) => (
              <li key={g} className="flex gap-2">
                <span aria-hidden className={cn("mt-[8px] size-1.5 shrink-0 rounded-full bg-current", h.tone)} />
                <span>{g}</span>
              </li>
            ))}
          </ul>
        ) : null}

        {verdict.claim_id || verdict.route ? (
          <dl className="grid gap-x-6 gap-y-1 font-mono text-[11px] text-muted-foreground sm:grid-cols-2">
            {verdict.claim_id ? (
              <div className="flex min-w-0 gap-2">
                <dt className="tracking-wider uppercase">claim</dt>
                <dd className="truncate">
                  <Link href={`/claims/${verdict.claim_id}`} className="text-primary underline-offset-2 hover:underline">
                    {verdict.claim_id}
                  </Link>
                  {verdict.claim_version_hash ? <span className="opacity-70"> @ {verdict.claim_version_hash}</span> : null}
                </dd>
              </div>
            ) : null}
            {verdict.route ? (
              <div className="flex min-w-0 gap-2">
                <dt className="tracking-wider uppercase">route</dt>
                <dd className="truncate">{verdict.route}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}

        {verdict.flags.length ? (
          <div className="flex flex-wrap gap-1.5">
            {verdict.flags.map((f) => (
              <FlagChip key={f} flag={f} />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

const BAND_TONE = { high: "text-status-ok", medium: "text-status-info", low: "text-status-warn" } as const;

/** Computed from the claim, the match and its evidence; it orders reading and never decides release. */
function ConfidencePill({ confidence }: { confidence: Confidence }) {
  return (
    <span
      className={cn("font-mono text-[10px] tracking-wider uppercase tabular-nums", BAND_TONE[confidence.band])}
      title="Computed from relevance, evidence, freshness and provenance. It orders review; the gates decide release."
      data-testid="confidence-pill"
      data-band={confidence.band}
    >
      {confidence.band} confidence {confidence.score.toFixed(2)}
    </span>
  );
}
