"use client";

import * as React from "react";
import { diffWords } from "diff";
import { cn } from "@/lib/utils";

/**
 * Word-level diff between the last approved answer and the current draft.
 * Insertions wear the ok wash, removals the critical wash with a strike;
 * unchanged text stays plain so the eye lands only on what moved.
 */
export function WordDiff({ before, after, className }: { before: string; after: string; className?: string }) {
  const parts = React.useMemo(() => (before ? diffWords(before, after) : []), [before, after]);

  const { added, removed } = React.useMemo(() => {
    let a = 0;
    let r = 0;
    for (const p of parts) {
      const n = p.value.split(/\s+/).filter(Boolean).length;
      if (p.added) a += n;
      else if (p.removed) r += n;
    }
    return { added: a, removed: r };
  }, [parts]);

  if (!before) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)} data-testid="word-diff-empty">
        No previously approved answer for this question
      </p>
    );
  }

  return (
    <div className={cn("space-y-2", className)} data-testid="word-diff">
      <p className="eyebrow" aria-live="polite">
        {added} {added === 1 ? "word" : "words"} added, {removed} removed
      </p>
      <p className="text-sm leading-relaxed">
        {parts.map((p, i) =>
          p.added ? (
            <ins key={i} className="rounded-xs bg-status-ok-wash text-status-ok no-underline">
              {p.value}
            </ins>
          ) : p.removed ? (
            <del key={i} className="rounded-xs bg-status-critical-wash text-status-critical line-through">
              {p.value}
            </del>
          ) : (
            <span key={i}>{p.value}</span>
          ),
        )}
      </p>
    </div>
  );
}
