"use client";

import * as React from "react";
import { Sparkles, CornerDownLeft } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { VerdictCard } from "@/components/verdict-card";
import { api, type Verdict } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The Ask bar lives in the top bar of every screen. Type a question, press
 * Enter, get the gate's verdict in under a second. Dry run: nothing is
 * drafted or sent. The command palette (cmd K) is for jumping.
 */
export function AskBar({ className }: { className?: string }) {
  const [query, setQuery] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<{ question: string; verdict: Verdict; ms: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "/" && !e.metaKey && !e.ctrlKey) {
        const t = e.target as HTMLElement | null;
        const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
        if (!typing) {
          e.preventDefault();
          inputRef.current?.focus();
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    const t0 = performance.now();
    try {
      const verdict = await api.ask(q);
      setResult({ question: q, verdict, ms: Math.round(performance.now() - t0) });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The ask failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={submit} className={cn("relative min-w-0 flex-1", className)} role="search" aria-label="Ask Constat">
        <Sparkles className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-primary" aria-hidden />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask: will we answer this question, and on what claim?"
          aria-label="Ask a question for a dry-run verdict"
          data-testid="ask-input"
          className="h-8 w-full rounded-md border bg-muted/60 pr-16 pl-8 text-sm placeholder:text-muted-foreground focus:bg-background focus-visible:outline-2 focus-visible:outline-ring"
        />
        <span className="pointer-events-none absolute top-1/2 right-2 flex -translate-y-1/2 items-center gap-1 text-muted-foreground">
          {busy ? <span className="eyebrow">gating</span> : query ? <CornerDownLeft className="size-3.5" aria-hidden /> : <Kbd>/</Kbd>}
        </span>
        {error ? <p className="absolute top-full left-0 mt-1 text-xs text-status-critical">{error}</p> : null}
      </form>

      <Dialog open={!!result} onOpenChange={(o) => !o && setResult(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading">Verdict</DialogTitle>
            <DialogDescription>
              Dry run in {result?.ms ?? 0} ms. Nothing was drafted into a questionnaire or sent.
            </DialogDescription>
          </DialogHeader>
          {result ? <VerdictCard verdict={result.verdict} question={result.question} /> : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
