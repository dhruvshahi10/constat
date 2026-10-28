import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  DIFFICULTY_LABEL,
  type Difficulty,
  type ItemState,
  type Outcome,
} from "@/lib/api";

/* Status colour vocabulary, shared by every screen so the same state always
   looks the same. Washes are backgrounds; the strong colour is the text. */

const STATE_TONE: Record<ItemState, string> = {
  RECEIVED: "text-muted-foreground bg-muted",
  NORMALISED: "text-muted-foreground bg-muted",
  MATCHED: "text-status-info bg-status-info-wash",
  DRAFTED: "text-status-info bg-status-info-wash",
  REVIEW: "text-status-warn bg-status-warn-wash",
  APPROVED: "text-status-ok bg-status-ok-wash",
  SENT: "text-status-ok bg-status-ok-wash",
  HELD: "text-status-warn bg-status-warn-wash",
  REFUSED: "text-status-critical bg-status-critical-wash",
  QUARANTINED: "text-status-critical bg-status-critical-wash",
};

export const STATE_LABEL: Record<ItemState, string> = {
  RECEIVED: "Received",
  NORMALISED: "Normalised",
  MATCHED: "Matched",
  DRAFTED: "Drafted",
  REVIEW: "In review",
  APPROVED: "Approved",
  SENT: "Sent",
  HELD: "Held",
  REFUSED: "Refused",
  QUARANTINED: "Quarantined",
};

const chip =
  "inline-flex h-5 items-center gap-1.5 rounded-sm border border-transparent px-1.5 font-mono text-[10px] uppercase tracking-[0.12em] whitespace-nowrap before:size-1.5 before:bg-current before:content-['']";

export function StateBadge({ state, className }: { state: ItemState; className?: string }) {
  return (
    <span className={cn(chip, STATE_TONE[state], className)} data-state={state}>
      {STATE_LABEL[state]}
    </span>
  );
}

const DIFFICULTY_TONE: Record<Difficulty, string> = {
  reused: "text-status-ok bg-status-ok-wash",
  covered: "text-status-info bg-status-info-wash",
  parameter_missing: "text-status-warn bg-status-warn-wash",
  novel: "text-status-critical bg-status-critical-wash",
  contractual: "text-status-critical bg-status-critical-wash",
};

export function DifficultyBadge({ difficulty, className }: { difficulty: Difficulty | null; className?: string }) {
  if (!difficulty) {
    return <span className={cn(chip, "text-muted-foreground bg-muted", className)}>Unclassed</span>;
  }
  return (
    <span className={cn(chip, DIFFICULTY_TONE[difficulty], className)} data-difficulty={difficulty}>
      {DIFFICULTY_LABEL[difficulty]}
    </span>
  );
}

const OUTCOME_TONE: Record<Outcome, string> = {
  ANSWER: "text-status-ok bg-status-ok-wash border-status-ok/40",
  HOLD_HUMAN: "text-status-warn bg-status-warn-wash border-status-warn/40",
  REFUSE: "text-status-critical bg-status-critical-wash border-status-critical/40",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  ANSWER: "Answer",
  HOLD_HUMAN: "Hold for a human",
  REFUSE: "Refuse",
};

export function OutcomeBadge({ outcome, className, size = "sm" }: { outcome: Outcome; className?: string; size?: "sm" | "lg" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border font-mono uppercase tracking-[0.14em]",
        size === "sm" ? "h-6 px-2 text-[11px]" : "h-9 px-3 text-sm",
        OUTCOME_TONE[outcome],
        className,
      )}
      data-outcome={outcome}
    >
      {outcome.replace("_", " ")}
    </span>
  );
}

export function FlagChip({ flag, className }: { flag: string; className?: string }) {
  return (
    <Badge variant="outline" className={cn("rounded-sm font-mono text-[10px] tracking-wider", className)}>
      {flag.replaceAll("_", " ")}
    </Badge>
  );
}

/** An exception that must travel with a claim into any answer that cites it. */
export function ExceptionChip({ text, carried, className }: { text: string; carried?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-start gap-1.5 rounded-sm border px-2 py-1 text-xs leading-snug",
        carried === false
          ? "border-status-critical/40 bg-status-critical-wash text-status-critical"
          : "border-status-warn/40 bg-status-warn-wash text-foreground",
        className,
      )}
      title={carried === false ? "This exception is missing from the answer" : "Exception carried into the answer"}
    >
      <span className="mt-[1px] font-mono text-[10px] uppercase tracking-wider opacity-80">
        {carried === false ? "dropped" : "exception"}
      </span>
      <span>{text}</span>
    </span>
  );
}
