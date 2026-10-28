"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { api, type Claim, type QuestionDetail } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { DifficultyBadge, ExceptionChip, StateBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/page-header";
import { VerdictCard } from "@/components/verdict-card";
import { WordDiff } from "@/components/word-diff";
import { RouteDialog, routeSuggestions } from "@/components/route-dialog";
import { isTypingTarget } from "@/components/screens/review-queue";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kbd } from "@/components/ui/kbd";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

/** null until mounted, so the first client render matches the server. */
function useMinWidthMd(): boolean | null {
  const [wide, setWide] = React.useState<boolean | null>(null);
  React.useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const apply = () => setWide(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return wide;
}

function daysUntil(iso: string): number {
  const target = new Date(`${iso}T00:00:00Z`).getTime();
  const today = new Date();
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target - now) / 86_400_000);
}

function expiryTone(days: number): { label: string; className: string } {
  if (days < 0) return { label: `expired ${Math.abs(days)}d ago`, className: "text-status-critical" };
  if (days <= 30) return { label: `expires in ${days}d`, className: "text-status-warn" };
  return { label: `valid ${days}d`, className: "text-status-ok" };
}

/** An exception travelled when its first 30 characters appear in the draft. */
function carriedInto(draft: string, exception: string): boolean {
  const needle = exception.slice(0, 30).trim().toLowerCase();
  if (!needle) return true;
  return draft.toLowerCase().includes(needle);
}

// ------------------------------------------------------------------ panes

function DraftPane({
  detail,
  editing,
  text,
  onText,
  onSave,
  onCancel,
  busy,
}: {
  detail: QuestionDetail;
  editing: boolean;
  text: string;
  onText: (t: string) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const { verdict, draft } = detail;
  const gated = verdict.outcome === "REFUSE" || verdict.outcome === "HOLD_HUMAN";
  const refuse = verdict.outcome === "REFUSE";
  const firstFlag = verdict.flags[0];

  if (editing) {
    return (
      <div className="space-y-3" data-testid="draft-pane">
        <label htmlFor="draft-editor" className="eyebrow">
          Edit the draft
        </label>
        <Textarea
          id="draft-editor"
          value={text}
          onChange={(e) => onText(e.target.value)}
          className="min-h-40 text-base leading-relaxed"
          autoFocus
          data-testid="draft-editor"
        />
        <p className="text-xs text-muted-foreground">
          Saving re-gates the answer. If it changes what a claim says, a proposal is opened for the claim owner.
        </p>
        <div className="flex gap-2">
          <Button onClick={onSave} disabled={busy || !text.trim()} data-testid="draft-save">
            {busy ? "Saving" : "Save"}
          </Button>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="space-y-4" data-testid="draft-pane">
        <EmptyState title="No draft was produced" body="The gate stopped this question before any answer was written." />
        <VerdictCard verdict={verdict} />
      </div>
    );
  }

  if (gated) {
    return (
      <div className="space-y-5" data-testid="draft-pane" data-gated={verdict.outcome}>
        <div className="relative pt-6">
          <div
            data-testid="gate-stamp"
            role="img"
            aria-label={`Gate stamp: ${refuse ? "refused" : "held"}${firstFlag ? `, ${firstFlag.replaceAll("_", " ").toLowerCase()}` : ""}`}
            className={cn(
              "gate-stamp pointer-events-none absolute -top-1 right-0 z-10 flex flex-col items-center rounded-sm border-2 bg-background/90 px-3 py-1 font-mono uppercase tracking-[0.2em]",
              refuse ? "border-status-critical text-status-critical" : "border-status-warn text-status-warn",
            )}
          >
            <span className="text-sm font-medium leading-tight">{refuse ? "REFUSED" : "HELD"}</span>
            {firstFlag ? <span className="text-[9px] leading-tight tracking-[0.12em] opacity-90">{firstFlag.replaceAll("_", " ")}</span> : null}
          </div>
          <p className="draft-struck inline box-decoration-clone text-base leading-relaxed" data-testid="draft-text">
            {draft}
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          The model wrote this with confidence. No claim lets it leave, so it does not.
        </p>
        <VerdictCard verdict={verdict} />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="draft-pane" data-gated="ANSWER">
      <p className="text-base leading-relaxed" data-testid="draft-text">
        {draft}
      </p>
      <VerdictCard verdict={verdict} compact />
    </div>
  );
}

function ClaimCard({ claim, draft }: { claim: Claim; draft: string }) {
  const days = daysUntil(claim.valid_until);
  const tone = expiryTone(days);
  const carried = claim.exceptions.map((x) => carriedInto(draft, x));
  const dropped = carried.some((c) => !c);
  return (
    <Card size="sm" data-testid={`claim-${claim.id}`}>
      <CardHeader>
        <CardTitle className="font-sans text-sm font-normal leading-snug">{claim.statement}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground sm:grid-cols-2">
          <div className="flex gap-2">
            <dt className="uppercase tracking-wider">owner</dt>
            <dd className="truncate text-foreground">{claim.owner}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="uppercase tracking-wider">valid until</dt>
            <dd className={tone.className}>
              {claim.valid_until} <span className="opacity-80">({tone.label})</span>
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="uppercase tracking-wider">version</dt>
            <dd className="text-foreground">{claim.version_hash}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="uppercase tracking-wider">status</dt>
            <dd>{claim.status}</dd>
          </div>
        </dl>
        {claim.exceptions.length ? (
          <div className="flex flex-col gap-1.5">
            {claim.exceptions.map((x, i) => (
              <ExceptionChip key={x} text={x} carried={carried[i]} />
            ))}
          </div>
        ) : null}
        {dropped ? (
          <p className="text-xs text-status-critical" role="alert">
            An exception did not travel into the draft
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ClaimsPane({ detail }: { detail: QuestionDetail }) {
  if (!detail.claims.length) {
    return (
      <div data-testid="claims-pane">
        <EmptyState title="No claim supports this draft" body="That is why it cannot be released." />
      </div>
    );
  }
  return (
    <div className="space-y-3" data-testid="claims-pane">
      {detail.claims.map((c) => (
        <ClaimCard key={c.id} claim={c} draft={detail.draft} />
      ))}
    </div>
  );
}

function DiffPane({ detail }: { detail: QuestionDetail }) {
  return (
    <div className="space-y-3" data-testid="diff-pane">
      {detail.last_approved_meta ? (
        <p className="text-xs text-muted-foreground">
          Against the answer approved for {detail.last_approved_meta.customer} on {detail.last_approved_meta.sent_on}.
        </p>
      ) : null}
      <WordDiff before={detail.last_approved_answer ?? ""} after={detail.draft} />
    </div>
  );
}

function PaneTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="eyebrow mb-3">{children}</h2>;
}

// ----------------------------------------------------------------- screen

export function ReviewDetail({ id, initialEdit }: { id: string; initialEdit?: boolean }) {
  const router = useRouter();
  const { href } = useEmbed();
  const wide = useMinWidthMd();
  const { data, error, loading, reload } = useAsync(() => api.getQuestion(id), [id]);

  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [routing, setRouting] = React.useState(false);
  const seeded = React.useRef(false);

  // ?edit=1 opens the editor as soon as the draft is known.
  React.useEffect(() => {
    if (initialEdit && data && !seeded.current) {
      seeded.current = true;
      setText(data.draft);
      setEditing(true);
    }
  }, [initialEdit, data]);

  const startEdit = React.useCallback(() => {
    if (!data || editing) return;
    setText(data.draft);
    setEditing(true);
  }, [data, editing]);

  const approve = React.useCallback(async () => {
    if (!data || busy) return;
    setBusy(true);
    try {
      await api.approve(id);
      toast.success("Approved", { description: `${data.item.customer}, question ${data.item.ordinal}` });
      reload();
    } catch (e) {
      toast.error("Could not approve", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }, [data, busy, id, reload]);

  const save = React.useCallback(async () => {
    if (busy || !text.trim()) return;
    setBusy(true);
    try {
      const res = await api.edit(id, text);
      setEditing(false);
      if (res.proposal) {
        toast("Edit saved; a claim change proposal was opened", {
          action: { label: "View proposals", onClick: () => router.push(href("/claims/proposals")) },
        });
      } else {
        toast.success("Edit saved");
      }
      reload();
    } catch (e) {
      toast.error("Could not save", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }, [busy, text, id, reload, router, href]);

  const send = React.useCallback(async () => {
    if (!data || busy || data.item.state !== "APPROVED") return;
    setBusy(true);
    try {
      await api.send(id);
      toast.success("Sent", { description: `Delivered to ${data.item.customer}` });
      reload();
    } catch (e) {
      toast.error("Could not send", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }, [data, busy, id, reload]);

  const route = React.useCallback(
    async (to: string, deadline: string) => {
      try {
        await api.route(id, to, deadline);
        toast.success(`Routed to ${to}`, { description: `Due ${deadline}` });
        reload();
      } catch (e) {
        toast.error("Could not route", { description: e instanceof Error ? e.message : String(e) });
        throw e;
      }
    },
    [id, reload],
  );

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (routing || editing || !data || isTypingTarget(e.target)) return;
      switch (e.key) {
        case "a":
          e.preventDefault();
          void approve();
          break;
        case "e":
          e.preventDefault();
          startEdit();
          break;
        case "r":
          e.preventDefault();
          setRouting(true);
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [routing, editing, data, approve, startEdit]);

  const suggestions = React.useMemo(() => routeSuggestions([data?.verdict.route, data?.item.route]), [data]);

  if (loading && !data) return <LoadingState label="Loading the question" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return null;

  const { item, verdict } = data;
  const canSend = item.state === "APPROVED";

  const actions = (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Review actions">
      <Button onClick={() => void approve()} disabled={busy || editing} data-testid="action-approve">
        Approve <Kbd className="ml-1 bg-primary-foreground/15 text-primary-foreground">a</Kbd>
      </Button>
      <Button variant="outline" onClick={startEdit} disabled={busy || editing} data-testid="action-edit">
        Edit <Kbd className="ml-1">e</Kbd>
      </Button>
      <Button variant="outline" onClick={() => setRouting(true)} disabled={busy || editing} data-testid="action-route">
        Route <Kbd className="ml-1">r</Kbd>
      </Button>
      <Button
        variant="secondary"
        onClick={() => void send()}
        disabled={busy || editing || !canSend}
        title={canSend ? "Send the approved answer" : "Approve before sending"}
        data-testid="action-send"
      >
        Send
      </Button>
    </div>
  );

  const draftPane = (
    <DraftPane detail={data} editing={editing} text={text} onText={setText} onSave={() => void save()} onCancel={() => setEditing(false)} busy={busy} />
  );
  const claimsPane = <ClaimsPane detail={data} />;
  const diffPane = <DiffPane detail={data} />;

  return (
    <div className="pb-24 md:pb-0" data-testid="review-detail" data-outcome={verdict.outcome}>
      <Link href={href("/review")} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft aria-hidden className="size-4" />
        Back to queue
      </Link>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="eyebrow">
              {item.customer} <span aria-hidden>/</span> Q{item.ordinal} <span aria-hidden>/</span> {item.domain}
            </span>
            <StateBadge state={item.state} />
            <DifficultyBadge difficulty={item.difficulty} />
            {item.blocks_deal ? (
              <span className="inline-flex h-5 items-center rounded-sm border border-status-critical/40 bg-status-critical-wash px-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-status-critical">
                blocks deal
              </span>
            ) : null}
          </div>
          <h1 className="mt-2 max-w-[60ch] font-heading text-2xl leading-snug font-normal tracking-tight sm:text-3xl">{item.text}</h1>
        </div>
        <div className="hidden md:block">{actions}</div>
      </header>

      {wide ? (
        <ResizablePanelGroup orientation="horizontal" className="min-h-[60vh] rounded-md border">
          <ResizablePanel defaultSize="42" minSize="25" className="overflow-auto p-4">
            <PaneTitle>Draft</PaneTitle>
            {draftPane}
          </ResizablePanel>
          <ResizableHandle withHandle aria-label="Resize draft and claims" />
          <ResizablePanel defaultSize="30" minSize="20" className="overflow-auto p-4">
            <PaneTitle>Claims used</PaneTitle>
            {claimsPane}
          </ResizablePanel>
          <ResizableHandle withHandle aria-label="Resize claims and diff" />
          <ResizablePanel defaultSize="28" minSize="20" className="overflow-auto p-4">
            <PaneTitle>Diff</PaneTitle>
            {diffPane}
          </ResizablePanel>
        </ResizablePanelGroup>
      ) : wide === false ? (
        <Tabs defaultValue="draft">
          <TabsList className="w-full">
            <TabsTrigger value="draft">Draft</TabsTrigger>
            <TabsTrigger value="claims">Claims</TabsTrigger>
            <TabsTrigger value="diff">Diff</TabsTrigger>
          </TabsList>
          <TabsContent value="draft" className="rounded-md border p-4">
            {draftPane}
          </TabsContent>
          <TabsContent value="claims" className="rounded-md border p-4">
            {claimsPane}
          </TabsContent>
          <TabsContent value="diff" className="rounded-md border p-4">
            {diffPane}
          </TabsContent>
        </Tabs>
      ) : null}

      <div className="fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 p-3 backdrop-blur md:hidden">{actions}</div>

      <RouteDialog open={routing} onOpenChange={setRouting} suggestions={suggestions} subject={`${item.customer}, question ${item.ordinal}`} onSubmit={route} />
    </div>
  );
}
