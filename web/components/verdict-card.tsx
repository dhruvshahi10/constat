import Link from "next/link";
import { cn } from "@/lib/utils";
import type { Verdict } from "@/lib/api";
import { DifficultyBadge, FlagChip, OutcomeBadge } from "@/components/badges";

/**
 * The gate's decision, rendered the same way everywhere: the command palette,
 * the question page and the embedded views all show this card.
 */
export function VerdictCard({ verdict, question, className, compact }: { verdict: Verdict; question?: string; className?: string; compact?: boolean }) {
  const tone =
    verdict.outcome === "ANSWER"
      ? "border-l-status-ok"
      : verdict.outcome === "HOLD_HUMAN"
        ? "border-l-status-warn"
        : "border-l-status-critical";
  return (
    <section
      className={cn("rounded-md border border-l-2 bg-card p-4 text-card-foreground", tone, className)}
      aria-label={`Verdict: ${verdict.outcome}`}
      data-testid="verdict-card"
    >
      <div className="flex flex-wrap items-center gap-2">
        <OutcomeBadge outcome={verdict.outcome} size={compact ? "sm" : "lg"} />
        <DifficultyBadge difficulty={verdict.difficulty} />
        {verdict.reused ? <span className="eyebrow">verbatim reuse</span> : null}
      </div>
      {question ? <p className="mt-3 text-sm text-muted-foreground">{question}</p> : null}

      {verdict.outcome === "ANSWER" && verdict.answer ? (
        <p className="mt-3 text-sm leading-relaxed">{verdict.answer}</p>
      ) : null}

      {verdict.gaps.length ? (
        <ul className="mt-3 space-y-1 text-sm">
          {verdict.gaps.map((g) => (
            <li key={g} className="flex gap-2">
              <span aria-hidden className="mt-[7px] size-1.5 shrink-0 bg-current opacity-60" />
              <span>{g}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <dl className="mt-3 grid gap-x-6 gap-y-1 font-mono text-[11px] text-muted-foreground sm:grid-cols-2">
        {verdict.claim_id ? (
          <div className="flex gap-2">
            <dt className="uppercase tracking-wider">claim</dt>
            <dd>
              <Link href={`/claims/${verdict.claim_id}`} className="text-primary underline-offset-2 hover:underline">
                {verdict.claim_id}
              </Link>
              {verdict.claim_version_hash ? <span className="opacity-70"> @ {verdict.claim_version_hash}</span> : null}
            </dd>
          </div>
        ) : null}
        {verdict.route ? (
          <div className="flex gap-2">
            <dt className="uppercase tracking-wider">route</dt>
            <dd>{verdict.route}</dd>
          </div>
        ) : null}
      </dl>

      {verdict.flags.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {verdict.flags.map((f) => (
            <FlagChip key={f} flag={f} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
