"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { api, type Claim, type QuestionDetail } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { DifficultyBadge, ExceptionChip, StateBadge } from "@/components/badges";
import { EmptyState, ErrorState } from "@/components/page-header";
import { DetailSkeleton } from "@/components/skeletons";
import { ProvenanceRail } from "@/components/provenance-rail";
import { VerdictCard } from "@/components/verdict-card";
import { WordDiff } from "@/components/word-diff";
import { RouteDialog, routeSuggestions } from "@/components/route-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Kbd } from "@/components/ui/kbd";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

/** True when a keystroke belongs to a field, not to the page. Checkboxes and buttons do not count. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT") {
    const type = (target as HTMLInputElement).type;
    return !["checkbox", "radio", "button", "submit", "reset"].includes(type);
  }
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return target.closest("[role=dialog], [role=menu], [role=listbox], [role=combobox], [contenteditable=true]") !== null;
}

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

function needleOf(exception: string): string {
  return exception.slice(0, 30).trim().toLowerCase();
}

/** An exception travelled when its first 30 characters appear in the draft. */
function carriedInto(draft: string, exception: string): boolean {
  const needle = needleOf(exception);
  if (!needle) return true;
  return draft.toLowerCase().includes(needle);
}

/**
 * Wrap the sentence(s) of a draft that carry a claim exception in a mark, so
 * the exception is seen travelling with the answer. Best effort: a sentence
 * carries an exception when it overlaps a case-insensitive match of the
 * exception's first 30 characters. Exceptions not found come back as missing.
 */
function markExceptions(draft: string, exceptions: string[]): { nodes: React.ReactNode[]; missing: string[] } {
  const lower = draft.toLowerCase();
  const ranges: Array<[number, number]> = [];
  const missing: string[] = [];
  for (const x of exceptions) {
    const needle = needleOf(x);
    if (!needle) continue;
    const at = lower.indexOf(needle);
    if (at === -1) missing.push(x);
    else ranges.push([at, at + needle.length]);
  }
  if (!ranges.length) return { nodes: [draft], missing };

  // Sentences end at . ! or ? followed by whitespace, so 99.9% stays whole.
  const segments: Array<{ start: number; end: number; sentence: boolean }> = [];
  const re = /([.!?])(\s+)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(draft)) !== null) {
    const end = m.index + 1;
    segments.push({ start: last, end, sentence: true });
    segments.push({ start: end, end: end + m[2].length, sentence: false });
    last = end + m[2].length;
  }
  if (last < draft.length) segments.push({ start: last, end: draft.length, sentence: true });

  const nodes = segments.map((s, i) => {
    const value = draft.slice(s.start, s.end);
    const carries = s.sentence && ranges.some(([a, b]) => a < s.end && b > s.start);
    return carries ? (
      <mark key={i} title="Exception carried from claim" className="box-decoration-clone rounded-sm bg-status-warn-wash px-0.5 text-foreground">
        {value}
      </mark>
    ) : (
      <React.Fragment key={i}>{value}</React.Fragment>
    );
  });
  return { nodes, missing };
}

function DroppedWarning({ missing }: { missing: string[] }) {
  if (!missing.length) return null;
  return (
    <div className="space-y-1.5" data-testid="exception-dropped">
      <p className="text-xs text-status-critical">
        {missing.length === 1 ? "An exception did not travel into the draft" : `${missing.length} exceptions did not travel into the draft`}
      </p>
      <div className="flex flex-col gap-1.5">
        {missing.map((x) => (
          <ExceptionChip key={x} text={x} carried={false} />
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ panes

function GateStamp({ refuse, flag }: { refuse: boolean; flag: string | undefined }) {
  const flagText = flag ? flag.replaceAll("_", " ") : null;
  return (
    <div
      data-testid="gate-stamp"
      role="img"
      aria-label={`Gate stamp: ${refuse ? "refused" : "held"}${flagText ? `, ${flagText.toLowerCase()}` : ""}`}
      className={cn(
        // The gate-stamp keyframes settle at -3deg; the extra -1deg here lands it at -4deg.
        "gate-stamp pointer-events-none absolute -top-1 right-1 z-10 flex -rotate-1 flex-col items-center rounded-sm border-[3px] bg-background/90 px-4 py-1.5 font-mono uppercase tracking-[0.24em] outline outline-1 outline-offset-[-6px]",
        refuse ? "border-status-critical text-status-critical outline-status-critical/50" : "border-status-warn text-status-warn outline-status-warn/50",
      )}
    >
      <span className="text-base font-semibold leading-tight">{refuse ? "REFUSED" : "HELD"}</span>
      {flagText ? <span className="mt-0.5 text-[10px] leading-tight tracking-[0.14em] opacity-90">{flagText}</span> : null}
    </div>
  );
}

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
  const exceptions = React.useMemo(() => detail.claims.flatMap((c) => c.exceptions), [detail.claims]);
  const preview = React.useMemo(() => markExceptions(editing ? text : draft, exceptions), [editing, text, draft, exceptions]);

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
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onCancel();
            } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              onSave();
            }
          }}
          className="min-h-40 text-base leading-relaxed"
          autoFocus
          data-testid="draft-editor"
        />
        <p className="text-xs text-muted-foreground">
          Saving re-gates the answer. If it changes what a claim says, a proposal is opened for the claim owner.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onSave} disabled={busy || !text.trim()} data-testid="draft-save">
            {busy ? "Saving" : "Save"}
          </Button>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Cancel <Kbd className="ml-1">Esc</Kbd>
          </Button>
        </div>
        {exceptions.length ? (
          <div className="space-y-2 rounded-md border border-dashed p-3" data-testid="draft-preview">
            <p className="eyebrow">Preview, with exceptions marked</p>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{preview.nodes}</p>
            <DroppedWarning missing={preview.missing} />
          </div>
        ) : null}
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
    const who = verdict.route ?? detail.item.route ?? "the security owner";
    return (
      <div className="space-y-5" data-testid="draft-pane" data-gated={verdict.outcome}>
        <div className="relative pt-10">
          <GateStamp refuse={refuse} flag={verdict.flags[0]} />
          <p className="draft-struck inline box-decoration-clone text-base leading-relaxed" data-testid="draft-text">
            {draft}
          </p>
          <p className="mt-3 text-sm text-muted-foreground" data-testid="gate-reason">
            {refuse ? `No claim lets this leave. Routed to ${who}.` : `A person decides this one. Routed to ${who}.`}
          </p>
        </div>
        <VerdictCard verdict={verdict} />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="draft-pane" data-gated="ANSWER">
      <p className="text-base leading-relaxed" data-testid="draft-text">
        {preview.nodes}
      </p>
      <DroppedWarning missing={preview.missing} />
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

function ClaimsPane({ detail, draft }: { detail: QuestionDetail; draft: string }) {
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
        <ClaimCard key={c.id} claim={c} draft={draft} />
      ))}
    </div>
  );
}

function DiffPane({ detail, draft }: { detail: QuestionDetail; draft: string }) {
  return (
    <div className="space-y-3" data-testid="diff-pane">
      {detail.last_approved_meta ? (
        <p className="text-xs text-muted-foreground">
          Against the answer approved for {detail.last_approved_meta.customer} on {detail.last_approved_meta.sent_on}.
        </p>
      ) : null}
      <WordDiff before={detail.last_approved_answer ?? ""} after={draft} />
    </div>
  );
}

function PaneTitle({ children, as: Tag = "h2" }: { children: React.ReactNode; as?: "h2" | "h3" }) {
  return <Tag className="eyebrow mb-3">{children}</Tag>;
}

// ----------------------------------------------------------------- screen

export interface ReviewDetailProps {
  id: string;
  initialEdit?: boolean;
  /** Rendered inside the review workbench pane: compact heading, stacked panes, no back link. */
  embedded?: boolean;
  /** Called after an approve, edit, route or send lands, so a surrounding queue can refresh. */
  onChange?: () => void;
}

export function ReviewDetail({ id, initialEdit, embedded = false, onChange }: ReviewDetailProps) {
  const router = useRouter();
  const { href } = useEmbed();
  const wide = useMinWidthMd();
  const { data, error, loading, reload } = useAsync(() => api.getQuestion(id), [id]);

  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [routing, setRouting] = React.useState(false);
  const seeded = React.useRef(false);

  const changed = React.useCallback(() => {
    reload();
    onChange?.();
  }, [reload, onChange]);

  // ?edit=1 opens the editor as soon as the draft is known.
  React.useEffect(() => {
    if (initialEdit && data && !seeded.current) {
      seeded.current = true;
      setText(data.draft);
      setEditing(true);
    }
  }, [initialEdit, data]);

  const refuse = data?.verdict.outcome === "REFUSE";
  const settled = data?.item.state === "APPROVED" || data?.item.state === "SENT";
  const canSend = data?.item.state === "APPROVED";

  const startEdit = React.useCallback(() => {
    if (!data || editing || data.item.state === "SENT") return;
    setText(data.draft);
    setEditing(true);
  }, [data, editing]);

  const approve = React.useCallback(async () => {
    if (!data || busy || settled) return;
    if (data.verdict.outcome === "REFUSE") {
      toast.error("A refused answer cannot be approved", { description: "No claim supports it. Route it to an owner who can write one." });
      return;
    }
    setBusy(true);
    try {
      await api.approve(id);
      toast.success("Approved", { description: `${data.item.customer}, question ${data.item.ordinal}` });
      changed();
    } catch (e) {
      toast.error("Could not approve", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }, [data, busy, settled, id, changed]);

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
      changed();
    } catch (e) {
      toast.error("Could not save", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }, [busy, text, id, changed, router, href]);

  const send = React.useCallback(async () => {
    if (!data || busy || data.item.state !== "APPROVED") return;
    setBusy(true);
    try {
      await api.send(id);
      toast.success("Sent", { description: `Delivered to ${data.item.customer}` });
      changed();
    } catch (e) {
      toast.error("Could not send", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }, [data, busy, id, changed]);

  const route = React.useCallback(
    async (to: string, deadline: string) => {
      try {
        await api.route(id, to, deadline);
        toast.success(`Routed to ${to}`, { description: `Due ${deadline}` });
        changed();
      } catch (e) {
        toast.error("Could not route", { description: e instanceof Error ? e.message : String(e) });
        throw e;
      }
    },
    [id, changed],
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
        case "s":
          if (canSend) {
            e.preventDefault();
            void send();
          }
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [routing, editing, data, canSend, approve, startEdit, send]);

  const suggestions = React.useMemo(() => routeSuggestions([data?.verdict.route, data?.item.route]), [data]);

  if (loading && !data) return <DetailSkeleton />;
  if (error) return <ErrorState error={error} />;
  if (!data) return null;

  const { item, verdict } = data;
  const liveDraft = editing ? text : data.draft;

  const actions = (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Review actions">
      <Button
        variant={canSend ? "outline" : "default"}
        onClick={() => void approve()}
        disabled={busy || editing || refuse || settled}
        title={refuse ? "A refused answer cannot be approved; route it" : settled ? "Already approved" : "Approve this answer"}
        data-testid="action-approve"
      >
        Approve <Kbd className={cn("ml-1", !canSend && "bg-primary-foreground/15 text-primary-foreground")}>a</Kbd>
      </Button>
      <Button variant="outline" onClick={startEdit} disabled={busy || editing || item.state === "SENT"} data-testid="action-edit">
        Edit <Kbd className="ml-1">e</Kbd>
      </Button>
      <Button variant="outline" onClick={() => setRouting(true)} disabled={busy || editing} data-testid="action-route">
        Route <Kbd className="ml-1">r</Kbd>
      </Button>
      <Button
        variant={canSend ? "default" : "ghost"}
        onClick={() => void send()}
        disabled={busy || editing || !canSend}
        title={canSend ? "Send the approved answer" : "Approve before sending"}
        data-testid="action-send"
      >
        Send <Kbd className={cn("ml-1", canSend && "bg-primary-foreground/15 text-primary-foreground")}>s</Kbd>
      </Button>
    </div>
  );

  const draftPane = (
    <DraftPane detail={data} editing={editing} text={text} onText={setText} onSave={() => void save()} onCancel={() => setEditing(false)} busy={busy} />
  );
  const claimsPane = <ClaimsPane detail={data} draft={liveDraft} />;
  const diffPane = <DiffPane detail={data} draft={liveDraft} />;

  const Heading = embedded ? "h2" : "h1";
  const header = (
    <header className={cn("flex flex-wrap items-start justify-between gap-4", embedded ? "mb-4" : "mb-6")}>
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
        <Heading
          className={cn(
            "mt-2 font-heading tracking-tight",
            embedded ? "text-[20px] leading-6 font-medium" : "max-w-[60ch] text-2xl leading-snug font-normal sm:text-3xl",
          )}
        >
          {item.text}
        </Heading>
        <ProvenanceRail item={item} verdict={verdict} claims={data.claims} className="mt-3" />
      </div>
      {embedded ? null : <div className="hidden md:block">{actions}</div>}
    </header>
  );

  if (embedded) {
    return (
      <div data-testid="review-detail" data-outcome={verdict.outcome} data-embedded="workbench">
        {header}
        <div className="mb-5">{actions}</div>
        <section aria-label="Draft" className="border-t pt-4">
          <PaneTitle as="h3">Draft</PaneTitle>
          {draftPane}
        </section>
        <section aria-label="Claims used" className="mt-6 border-t pt-4">
          <PaneTitle as="h3">Claims used</PaneTitle>
          {claimsPane}
        </section>
        <details className="group mt-6 border-t pt-4">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
            <ChevronRight aria-hidden className="size-4 transition-transform group-open:rotate-90" />
            Show diff against last approved
          </summary>
          <div className="mt-3">{diffPane}</div>
        </details>
        <RouteDialog open={routing} onOpenChange={setRouting} suggestions={suggestions} subject={`${item.customer}, question ${item.ordinal}`} onSubmit={route} />
      </div>
    );
  }

  return (
    <div className="pb-24 md:pb-0" data-testid="review-detail" data-outcome={verdict.outcome}>
      <Link href={href("/review")} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft aria-hidden className="size-4" />
        Back to queue
      </Link>

      {header}

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
