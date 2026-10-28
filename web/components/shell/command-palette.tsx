"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Sparkles, Search } from "lucide-react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { VerdictCard } from "@/components/verdict-card";
import { NAV_ITEMS } from "@/components/shell/nav";
import { api, type Verdict } from "@/lib/api";

/**
 * Cmd-K. Navigation plus "Ask": a dry-run verdict from POST /questions/ask.
 * The palette answers or refuses; it never sends anything to a customer.
 */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [asking, setAsking] = React.useState(false);
  const [asked, setAsked] = React.useState<{ question: string; verdict: Verdict } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  React.useEffect(() => {
    if (!open) {
      setQuery("");
      setAsked(null);
      setError(null);
      setAsking(false);
    }
  }, [open]);

  const ask = React.useCallback(async () => {
    const q = query.trim();
    if (!q || asking) return;
    setAsking(true);
    setError(null);
    try {
      const verdict = await api.ask(q);
      setAsked({ question: q, verdict });
    } catch (e) {
      setError(e instanceof Error ? e.message : "The ask failed");
    } finally {
      setAsking(false);
    }
  }, [query, asking]);

  const q = query.trim().toLowerCase();
  const navMatches = NAV_ITEMS.filter((n) => !q || n.label.toLowerCase().includes(q));
  const looksLikeQuestion = q.length > 12 || q.includes(" ") || q.endsWith("?");

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="gap-2 text-muted-foreground"
        onClick={() => setOpen(true)}
        aria-label="Open the command palette"
        data-testid="open-palette"
      >
        <Search aria-hidden />
        <span className="hidden lg:inline">Jump</span>
        <Kbd className="hidden lg:inline-flex">cmd K</Kbd>
      </Button>

      <CommandDialog open={open} onOpenChange={setOpen} title="Ask or jump" description="Type a question for a dry-run verdict, or a page name to jump to it." className="max-w-2xl">
        <Command shouldFilter={false} loop>
          <CommandInput
            placeholder="Ask a question, or jump to a page"
            value={query}
            onValueChange={setQuery}
            onKeyDown={(e) => {
              if (e.key === "Enter" && looksLikeQuestion && !asked) {
                e.preventDefault();
                void ask();
              }
            }}
          />
          <CommandList className="max-h-[70vh]">
            {asked ? (
              <div className="p-3">
                <VerdictCard verdict={asked.verdict} question={asked.question} />
                <p className="mt-2 text-xs text-muted-foreground">
                  Dry run. Nothing was drafted into a questionnaire or sent.
                </p>
              </div>
            ) : (
              <>
                <CommandEmpty>Nothing matches.</CommandEmpty>
                {q ? (
                  <CommandGroup heading="Ask">
                    <CommandItem value="ask" onSelect={() => void ask()} disabled={asking} data-testid="palette-ask">
                      <Sparkles aria-hidden />
                      <span className="truncate">{asking ? "Gating" : `Ask: ${query.trim()}`}</span>
                    </CommandItem>
                  </CommandGroup>
                ) : null}
                {error ? <p className="px-3 py-2 text-xs text-status-critical">{error}</p> : null}
                {navMatches.length ? (
                  <>
                    {q ? <CommandSeparator /> : null}
                    <CommandGroup heading="Jump to">
                      {navMatches.map((n) => {
                        const Icon = n.icon;
                        return (
                          <CommandItem
                            key={n.href}
                            value={n.href}
                            onSelect={() => {
                              setOpen(false);
                              router.push(n.href);
                            }}
                          >
                            <Icon aria-hidden />
                            {n.label}
                          </CommandItem>
                        );
                      })}
                    </CommandGroup>
                  </>
                ) : null}
              </>
            )}
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
