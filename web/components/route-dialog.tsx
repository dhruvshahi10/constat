"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/** Owners every route dialog offers, after the ones the verdicts suggested. */
export const DEFAULT_ROUTE_OWNERS = ["legal@northwind.example", "marcus@northwind.example"] as const;

/** Distinct, non-empty owners in the order given, then the defaults. */
export function routeSuggestions(candidates: Array<string | null | undefined>): string[] {
  const out: string[] = [];
  for (const c of [...candidates, ...DEFAULT_ROUTE_OWNERS]) {
    if (c && !out.includes(c)) out.push(c);
  }
  return out;
}

function isoDaysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export interface RouteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  suggestions: string[];
  onSubmit: (to: string, deadline: string) => void | Promise<void>;
  /** Shown in the description so the reviewer knows which item is leaving their hands. */
  subject?: string;
}

/**
 * Route a question to a human owner with a deadline. Shared by the queue and
 * the detail page so the two never drift.
 */
export function RouteDialog({ open, onOpenChange, suggestions, onSubmit, subject }: RouteDialogProps) {
  const [to, setTo] = React.useState<string>(suggestions[0] ?? "");
  const [deadline, setDeadline] = React.useState<string>(() => isoDaysFromNow(7));
  const [busy, setBusy] = React.useState(false);

  // Reset to a sensible default each time the dialog opens.
  React.useEffect(() => {
    if (open) {
      setTo(suggestions[0] ?? "");
      setDeadline(isoDaysFromNow(7));
      setBusy(false);
    }
  }, [open, suggestions]);

  const canSubmit = Boolean(to) && Boolean(deadline) && !busy;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    try {
      await onSubmit(to, deadline);
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="contents">
          <DialogHeader>
            <DialogTitle>Route to a person</DialogTitle>
            <DialogDescription>
              {subject ? `${subject}. ` : ""}
              Pick an owner and a date by which they must answer. The question is held until they do.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <span id="route-owner-label" className="eyebrow">
                Owner
              </span>
              <Select value={to} onValueChange={(v) => setTo(v ?? "")}>
                <SelectTrigger className="w-full" aria-labelledby="route-owner-label" data-testid="route-owner">
                  <SelectValue placeholder="Choose an owner" />
                </SelectTrigger>
                <SelectContent>
                  {suggestions.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <label htmlFor="route-deadline" className="eyebrow">
                Deadline
              </label>
              <Input
                id="route-deadline"
                type="date"
                value={deadline}
                min={isoDaysFromNow(0)}
                onChange={(e) => setDeadline(e.target.value)}
                required
                data-testid="route-deadline"
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} data-testid="route-submit">
              {busy ? "Routing" : "Route"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
