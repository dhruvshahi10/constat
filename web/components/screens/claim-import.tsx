"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowRight, CheckCircle2, FileText, Info, Lock, RotateCcw, UploadCloud } from "lucide-react";
import { api, type Audience, type ImportCommitResult, type ImportPreview, type ImportRow } from "@/lib/api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { ErrorState, PageHeader } from "@/components/page-header";
import { SummaryStrip, type SummaryStat } from "@/components/summary-strip";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress, ProgressLabel } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/* ------------------------------------------------------------------ */
/* Import: a completed questionnaire becomes draft claims with owners, */
/* not a flat answer library. Nothing imported is ever verified; every */
/* new claim opens as a proposal a second person must approve.         */
/* ------------------------------------------------------------------ */

type Action = ImportRow["action"];
type Step = "upload" | "review" | "done";

interface Decision {
  action: Action;
  owner: string | null;
}

const ACCEPT = [".xlsx", ".csv", ".docx"] as const;

const NORTHWIND_OWNERS = [
  "priya@northwind.example",
  "marcus@northwind.example",
  "lena@northwind.example",
  "tomas@northwind.example",
] as const;

const AUDIENCES: { value: Audience; label: string }[] = [
  { value: "public", label: "Public" },
  { value: "nda", label: "Under NDA" },
  { value: "internal", label: "Internal" },
];

const ACTIONS: { value: Action; label: string }[] = [
  { value: "new_claim", label: "New claim" },
  { value: "attach_answer", label: "Attach" },
  { value: "skip", label: "Skip" },
];

/** Sentinel for the owner select; Base UI keeps string values simplest. */
const UNASSIGNED = "__unassigned__";

const LOW_CONFIDENCE = 0.8;

const HEAD = "sticky top-0 z-10 h-8 bg-card px-3 text-[11px] font-medium text-muted-foreground shadow-[inset_0_-1px_0_var(--border)]";
const CELL = "h-9 px-3 py-0";

interface RowPolicy {
  /** Locked to Skip; the reviewer cannot change it. */
  locked: string | null;
  /** May attach or skip, but can never open a new claim. */
  noNewClaim: string | null;
}

/**
 * Injection rows are always locked to Skip. Contractual wording never opens a
 * claim: it locks to Skip, unless the importer already matched it to a
 * verified claim, in which case the reviewer may still attach or skip.
 */
function rowPolicy(row: ImportRow): RowPolicy {
  if (/injection/i.test(row.reason)) return { locked: "Injection pattern: quarantined, never imported", noNewClaim: null };
  if (/contractual/i.test(row.reason)) {
    if (row.action === "attach_answer" && row.existing_claim_id) {
      return { locked: null, noNewClaim: "Contractual framing never opens a new claim" };
    }
    return { locked: "Contractual wording: legal decides per deal", noNewClaim: null };
  }
  return { locked: null, noNewClaim: null };
}

function hasAllowedExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPT.some((ext) => lower.endsWith(ext));
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function commitLabel(proposals: number, attached: number): string {
  if (proposals === 0 && attached === 0) return "Nothing to import";
  if (attached === 0) return `Open ${plural(proposals, "proposal", "proposals")}`;
  if (proposals === 0) return `Attach ${plural(attached, "answer", "answers")}`;
  return `Open ${plural(proposals, "proposal", "proposals")} and attach ${plural(attached, "answer", "answers")}`;
}

/* ------------------------------------------------------------------ steps */

function Stepper({ step }: { step: Step }) {
  const steps: { id: Step; label: string }[] = [
    { id: "upload", label: "Upload" },
    { id: "review", label: "Review" },
    { id: "done", label: "Commit" },
  ];
  const current = steps.findIndex((s) => s.id === step);
  return (
    <ol aria-label="Import steps" className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1">
      {steps.map((s, i) => {
        const state = step === "done" || i < current ? "done" : i === current ? "current" : "todo";
        return (
          <li key={s.id} className="flex items-center gap-2" aria-current={state === "current" ? "step" : undefined}>
            <span
              className={cn(
                "inline-flex size-5 items-center justify-center rounded-sm border font-mono text-[10.5px] tabular-nums",
                state === "current" && "border-primary bg-primary text-primary-foreground",
                state === "done" && "border-status-ok/50 bg-status-ok-wash text-status-ok",
                state === "todo" && "text-muted-foreground",
              )}
            >
              {i + 1}
            </span>
            <span className={cn("text-[13px]", state === "todo" ? "text-muted-foreground" : "text-foreground font-medium")}>{s.label}</span>
            {i < steps.length - 1 ? <span aria-hidden className="mx-1 h-px w-8 bg-border" /> : null}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ upload */

function DropZone({ file, onFile, disabled, error }: { file: File | null; onFile: (f: File | null) => void; disabled: boolean; error: string | null }) {
  const [over, setOver] = React.useState(false);
  return (
    <div className="min-w-0">
      <label
        htmlFor="import-file"
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!disabled) onFile(e.dataTransfer.files?.[0] ?? null);
        }}
        className={cn(
          "flex min-h-52 cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed bg-card px-6 py-8 text-center transition-colors",
          "focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 hover:border-primary/60",
          over && "border-primary bg-primary/5",
          error && "border-status-critical/60",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        <input
          id="import-file"
          type="file"
          accept={ACCEPT.join(",")}
          className="sr-only"
          disabled={disabled}
          aria-describedby="import-file-hint"
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <>
            <FileText className="size-6 text-primary" aria-hidden />
            <span className="max-w-full truncate font-mono text-[13px]" title={file.name}>
              {file.name}
            </span>
            <span className="font-mono text-[11px] text-muted-foreground tabular-nums">{fmtSize(file.size)}</span>
            <span className="text-xs text-primary">Choose a different file</span>
          </>
        ) : (
          <>
            <UploadCloud className="size-6 text-muted-foreground" aria-hidden />
            <span className="font-heading text-base font-semibold">Drop a completed questionnaire</span>
            <span className="text-[13px] text-muted-foreground">
              or <span className="text-primary underline underline-offset-2">browse your files</span>
            </span>
          </>
        )}
        <span id="import-file-hint" className="font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
          {ACCEPT.join("  ")}
        </span>
      </label>
      {error ? (
        <p role="alert" className="mt-1.5 text-xs text-status-critical">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function UploadStep({ onPreview }: { onPreview: (p: ImportPreview) => void }) {
  const [file, setFile] = React.useState<File | null>(null);
  const [fileError, setFileError] = React.useState<string | null>(null);
  const [customer, setCustomer] = React.useState("");
  const [audience, setAudience] = React.useState<Audience>("nda");
  const [uploading, setUploading] = React.useState(false);
  const [pct, setPct] = React.useState(0);
  const [error, setError] = React.useState<Error | null>(null);

  // The API answers in one response, so the bar eases toward 92% and jumps to done.
  React.useEffect(() => {
    if (!uploading) return;
    setPct(6);
    const t = setInterval(() => setPct((p) => p + (92 - p) * 0.08), 80);
    return () => clearInterval(t);
  }, [uploading]);

  function pick(f: File | null) {
    if (!f) return;
    if (!hasAllowedExtension(f.name)) {
      setFile(null);
      setFileError(`${f.name} is not a supported file. Use ${ACCEPT.join(", ")}.`);
      return;
    }
    setFileError(null);
    setFile(f);
  }

  const canSubmit = Boolean(file) && customer.trim().length > 0 && !uploading;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !canSubmit) return;
    setError(null);
    setUploading(true);
    try {
      const preview = await api.importAnswers(file, { customer: customer.trim(), audience });
      setPct(100);
      onPreview(preview);
    } catch (err) {
      const e2 = err instanceof Error ? err : new Error(String(err));
      setError(e2);
      toast.error(e2.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]" aria-busy={uploading}>
      <DropZone file={file} onFile={pick} disabled={uploading} error={fileError} />

      <div className="flex flex-col gap-3 rounded-md border bg-card p-3">
        <div className="grid gap-1.5">
          <label htmlFor="import-customer" className="eyebrow">
            Customer
          </label>
          <Input
            id="import-customer"
            value={customer}
            onChange={(e) => setCustomer(e.target.value)}
            placeholder="Who the questionnaire was for"
            autoComplete="off"
            disabled={uploading}
            required
          />
        </div>

        <div className="grid gap-1.5">
          <span id="import-audience-label" className="eyebrow">
            Audience
          </span>
          <Select value={audience} onValueChange={(v) => setAudience((v as Audience | null) ?? "nda")} disabled={uploading}>
            <SelectTrigger className="w-full" aria-labelledby="import-audience-label">
              <SelectValue>{(v: Audience) => AUDIENCES.find((a) => a.value === v)?.label ?? v}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {AUDIENCES.map((a) => (
                <SelectItem key={a.value} value={a.value}>
                  {a.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-[11px] text-muted-foreground">Sets who may see the claims these answers become.</p>
        </div>

        <p className="rounded-sm border-l-2 border-status-info bg-status-info-wash px-2.5 py-2 text-xs leading-relaxed text-muted-foreground">
          Answers become proposals, never verified claims. A second person approves each one.
        </p>

        <Button type="submit" disabled={!canSubmit} className="mt-auto w-full">
          {uploading ? "Reading the file" : "Build the preview"}
        </Button>
      </div>

      {uploading ? (
        <div className="rounded-md border bg-card px-3 py-2.5 lg:col-span-2" aria-live="polite">
          <Progress value={Math.round(pct)} aria-label="Import progress">
            <ProgressLabel className="text-xs font-normal text-muted-foreground">
              Reading answers, clustering the ones that say the same thing, and matching existing claims
            </ProgressLabel>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground tabular-nums">{Math.round(pct)}%</span>
          </Progress>
        </div>
      ) : null}

      {error ? (
        <div className="lg:col-span-2">
          <ErrorState error={error} />
        </div>
      ) : null}
    </form>
  );
}

/* ------------------------------------------------------------------ review */

function ConfidenceCell({ value }: { value: number }) {
  const low = value < LOW_CONFIDENCE;
  const pct = Math.round(value * 100);
  return (
    <span className="inline-flex items-center gap-2" title={low ? "Below 80%: check the cluster before committing" : undefined}>
      <span aria-hidden className="relative h-1 w-10 overflow-hidden rounded-[1px] bg-muted">
        <span className={cn("absolute inset-y-0 left-0", low ? "bg-status-warn" : "bg-status-ok")} style={{ width: `${pct}%` }} />
      </span>
      <span className={cn("font-mono text-[11px] tabular-nums", low ? "text-status-warn" : "text-foreground")}>{pct}%</span>
    </span>
  );
}

function ActionControl({ row, value, policy, onChange }: { row: ImportRow; value: Action; policy: RowPolicy; onChange: (a: Action) => void }) {
  const { locked, noNewClaim } = policy;
  return (
    <div className="flex items-center gap-1.5" title={locked ?? noNewClaim ?? undefined}>
      {locked ? <Lock className="size-3.5 shrink-0 text-muted-foreground" aria-label={`Locked. ${locked}`} /> : null}
      <div role="group" aria-label={`Action for row ${row.ordinal}`} className="inline-flex rounded-md border bg-background/40 p-0.5">
        {ACTIONS.map((a) => {
          const noTarget = a.value === "attach_answer" && !row.existing_claim_id;
          const barred = a.value === "new_claim" && Boolean(noNewClaim);
          const disabled = Boolean(locked) || noTarget || barred;
          const active = value === a.value;
          return (
            <button
              key={a.value}
              type="button"
              aria-pressed={active}
              disabled={disabled}
              onClick={() => onChange(a.value)}
              title={noTarget ? "No existing claim covers this cluster" : barred ? (noNewClaim ?? undefined) : undefined}
              className={cn(
                "inline-flex h-6 items-center rounded-[3px] px-2 text-[11.5px] whitespace-nowrap transition-colors disabled:cursor-not-allowed",
                active && a.value === "new_claim" && "bg-primary text-primary-foreground",
                active && a.value === "attach_answer" && "bg-status-ok-wash text-status-ok",
                active && a.value === "skip" && "bg-muted text-foreground",
                !active && "text-muted-foreground hover:text-foreground disabled:text-muted-foreground/40 disabled:hover:text-muted-foreground/40",
              )}
            >
              {a.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function OwnerControl({ ordinal, owner, options, missing, onChange }: { ordinal: number; owner: string | null; options: string[]; missing: boolean; onChange: (o: string | null) => void }) {
  return (
    <Select value={owner ?? UNASSIGNED} onValueChange={(v) => onChange(!v || v === UNASSIGNED ? null : String(v))}>
      <SelectTrigger
        size="sm"
        aria-label={`Owner for row ${ordinal}`}
        aria-invalid={missing || undefined}
        className={cn("h-7 w-full max-w-[13rem] font-mono text-[11px]", missing && "border-status-critical text-status-critical")}
      >
        <SelectValue>
          {(v: string) =>
            v === UNASSIGNED ? (
              <span className={missing ? "font-sans text-status-critical" : "font-sans text-muted-foreground"}>{missing ? "Needs an owner" : "Unassigned"}</span>
            ) : (
              <span className="truncate">{v}</span>
            )
          }
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={UNASSIGNED}>
          <span className="text-muted-foreground">Unassigned</span>
        </SelectItem>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            <span className="font-mono text-[12px]">{o}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ReasonTip({ row, decision }: { row: ImportRow; decision: Decision }) {
  const detail = decision.action === "attach_answer" && row.existing_claim_id ? `Attaches to ${row.existing_claim_id}.` : null;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            className="inline-flex size-6 items-center justify-center rounded-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={`Why: ${row.reason}${detail ? ` ${detail}` : ""}`}
          />
        }
      >
        <Info className="size-3.5" aria-hidden />
      </TooltipTrigger>
      <TooltipContent side="left" className="block max-w-sm text-left leading-snug">
        <span className="block">{row.reason}</span>
        {detail ? <span className="mt-1 block font-mono text-[11px] opacity-80">{detail}</span> : null}
      </TooltipContent>
    </Tooltip>
  );
}

function ReviewStep({
  preview,
  onCommitted,
  onRestart,
}: {
  preview: ImportPreview;
  onCommitted: (r: ImportCommitResult) => void;
  onRestart: () => void;
}) {
  const [decisions, setDecisions] = React.useState<Record<number, Decision>>(() =>
    Object.fromEntries(
      preview.rows.map((r) => [r.ordinal, rowPolicy(r).locked ? { action: "skip" as const, owner: null } : { action: r.action, owner: r.suggested_owner }]),
    ),
  );
  const [committing, setCommitting] = React.useState(false);
  const [error, setError] = React.useState<Error | null>(null);

  const ownerOptions = React.useMemo(() => {
    const set = new Set<string>(NORTHWIND_OWNERS);
    for (const r of preview.rows) if (r.suggested_owner) set.add(r.suggested_owner);
    for (const o of preview.owners ?? []) set.add(o);
    return [...set];
  }, [preview.rows]);

  const set = (ordinal: number, patch: Partial<Decision>) => setDecisions((d) => ({ ...d, [ordinal]: { ...d[ordinal], ...patch } }));

  // One claim per cluster: rows that ask the same thing become one proposal.
  const tally = React.useMemo(() => {
    const t = { new_claim: 0, attach_answer: 0, skip: 0 };
    const newClusters = new Set<string>();
    for (const r of preview.rows) {
      const action = decisions[r.ordinal].action;
      if (action === "new_claim") newClusters.add(r.cluster || `row-${r.ordinal}`);
      else t[action] += 1;
    }
    t.new_claim = newClusters.size;
    return t;
  }, [preview.rows, decisions]);

  // A cluster needs one owner; any of its rows may carry it.
  const ownedClusters = new Set(
    preview.rows
      .filter((r) => decisions[r.ordinal].action === "new_claim" && decisions[r.ordinal].owner)
      .map((r) => r.cluster || `row-${r.ordinal}`),
  );
  const needsOwner = preview.rows.filter(
    (r) => decisions[r.ordinal].action === "new_claim" && !ownedClusters.has(r.cluster || `row-${r.ordinal}`),
  );
  const lowConfidence = preview.rows.filter((r) => r.confidence < LOW_CONFIDENCE).length;
  const avg = preview.rows.length ? preview.rows.reduce((n, r) => n + r.confidence, 0) / preview.rows.length : 0;
  const clusters = new Set(preview.rows.map((r) => r.cluster)).size;
  const lockedCount = preview.rows.filter((r) => rowPolicy(r).locked).length;

  const stats: SummaryStat[] = [
    { label: "New claims", value: tally.new_claim, tone: "info", hint: "open as proposals" },
    { label: "Attach to existing", value: tally.attach_answer, tone: "ok", hint: "join a verified claim" },
    { label: "Skipped", value: tally.skip, hint: lockedCount ? `${lockedCount} locked by policy` : "not imported" },
    {
      label: "Average confidence",
      value: `${Math.round(avg * 100)}%`,
      tone: avg < LOW_CONFIDENCE ? "warn" : "default",
      hint: lowConfidence ? `${lowConfidence} under 80%` : `${clusters} clusters`,
    },
  ];

  const blocked = needsOwner.length > 0;
  const nothing = tally.new_claim === 0 && tally.attach_answer === 0;

  async function commit() {
    if (blocked || nothing) return;
    setCommitting(true);
    setError(null);
    try {
      const result = await api.commitImport(
        preview.id,
        preview.rows.map((r) => {
          const d = decisions[r.ordinal];
          return { ordinal: r.ordinal, action: d.action, owner: d.action === "skip" ? null : d.owner };
        }),
      );
      onCommitted(result);
    } catch (err) {
      const e2 = err instanceof Error ? err : new Error(String(err));
      setError(e2);
      toast.error(e2.message);
    } finally {
      setCommitting(false);
    }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <FileText className="size-4 text-muted-foreground" aria-hidden />
        <span className="font-mono text-[13px]">{preview.filename}</span>
        <span className="text-[13px] text-muted-foreground">
          for <span className="text-foreground">{preview.customer}</span>, {plural(preview.rows.length, "answer", "answers")}
        </span>
        <span className="font-mono text-[11px] text-muted-foreground">{preview.id}</span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onRestart} disabled={committing}>
          <RotateCcw aria-hidden />
          Start over
        </Button>
      </div>

      <SummaryStrip stats={stats} className="mb-4 sm:grid-cols-4 md:grid-cols-4" />

      <div className="max-h-[65vh] overflow-auto rounded-md border bg-card">
        <table data-slot="table" className="w-full min-w-[1120px] text-[13px] tabular-nums">
          <TableHeader className="[&_tr]:border-b-0">
            <TableRow className="hover:bg-transparent">
              <TableHead scope="col" className={cn(HEAD, "w-10")}>#</TableHead>
              <TableHead scope="col" className={HEAD}>Question</TableHead>
              <TableHead scope="col" className={HEAD}>Imported answer</TableHead>
              <TableHead scope="col" className={HEAD}>Cluster</TableHead>
              <TableHead scope="col" className={HEAD}>Confidence</TableHead>
              <TableHead scope="col" className={HEAD}>Action</TableHead>
              <TableHead scope="col" className={HEAD}>Owner</TableHead>
              <TableHead scope="col" className={cn(HEAD, "w-10")}>
                <span className="sr-only">Reason</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {preview.rows.map((r) => {
              const d = decisions[r.ordinal];
              const policy = rowPolicy(r);
              const locked = policy.locked;
              const missing = d.action === "new_claim" && !d.owner && !ownedClusters.has(r.cluster || `row-${r.ordinal}`);
              return (
                <TableRow
                  key={r.ordinal}
                  data-locked={locked ? "true" : undefined}
                  className={cn(
                    locked && "bg-muted/30",
                    missing && "shadow-[inset_2px_0_0_var(--status-critical)]",
                  )}
                >
                  <TableCell className={cn(CELL, "font-mono text-xs text-muted-foreground")}>{r.ordinal}</TableCell>
                  <TableCell className={cn(CELL, "w-[30%] max-w-0")}>
                    <span className={cn("block truncate", locked && "text-muted-foreground")} title={r.question}>
                      {r.question}
                    </span>
                  </TableCell>
                  <TableCell className={cn(CELL, "w-[22%] max-w-0")}>
                    <span className="block truncate text-muted-foreground" title={r.answer || "No answer"}>
                      {r.answer || <span className="italic opacity-70">no answer</span>}
                    </span>
                  </TableCell>
                  <TableCell className={cn(CELL, "max-w-[10rem]")}>
                    <span
                      className="inline-block max-w-full truncate rounded-sm bg-muted px-1.5 py-px align-middle font-mono text-[10.5px]"
                      title={r.existing_claim_id ? `${r.cluster}, covered by ${r.existing_claim_id}` : r.cluster}
                    >
                      {r.cluster}
                    </span>
                  </TableCell>
                  <TableCell className={CELL}>
                    <ConfidenceCell value={r.confidence} />
                  </TableCell>
                  <TableCell className={CELL}>
                    <ActionControl row={r} value={d.action} policy={policy} onChange={(action) => set(r.ordinal, { action })} />
                  </TableCell>
                  <TableCell className={cn(CELL, "w-[13rem]")}>
                    {locked ? (
                      <span className="font-mono text-[11px] text-muted-foreground">not imported</span>
                    ) : d.action === "skip" ? (
                      <span className="font-mono text-[11px] text-muted-foreground">skipped</span>
                    ) : (
                      <OwnerControl ordinal={r.ordinal} owner={d.owner} options={ownerOptions} missing={missing} onChange={(owner) => set(r.ordinal, { owner })} />
                    )}
                  </TableCell>
                  <TableCell className={cn(CELL, "text-right")}>
                    <ReasonTip row={r} decision={d} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md border bg-card px-3 py-2.5">
        <div className="min-w-0 flex-1 text-xs leading-relaxed">
          {blocked ? (
            <p role="alert" className="text-status-critical">
              {plural(needsOwner.length, "new claim needs", "new claims need")} an owner before commit (row{needsOwner.length === 1 ? "" : "s"}{" "}
              {needsOwner.map((r) => r.ordinal).join(", ")}).
            </p>
          ) : (
            <p className="text-muted-foreground">
              New claims open as proposals in the draft state. Attached answers join the reuse corpus of a verified claim. Nothing becomes verified here.
            </p>
          )}
        </div>
        <Button onClick={commit} disabled={blocked || nothing || committing}>
          {committing ? "Committing" : commitLabel(tally.new_claim, tally.attach_answer)}
        </Button>
      </div>

      {error ? (
        <div className="mt-3">
          <ErrorState error={error} />
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ done */

function DoneStep({ preview, result, onRestart }: { preview: ImportPreview; result: ImportCommitResult; onRestart: () => void }) {
  const { href } = useEmbed();
  return (
    <section aria-labelledby="import-done" className="rounded-md border bg-card">
      <div className="flex flex-wrap items-start gap-3 border-b px-4 py-3">
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-status-ok" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 id="import-done" className="font-heading text-lg leading-tight font-semibold">
            Import committed
          </h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            <span className="font-mono">{preview.filename}</span> for {preview.customer}. Each proposal now waits for a second person; nothing became a verified claim.
          </p>
        </div>
      </div>
      <SummaryStrip
        className="rounded-none border-x-0 border-t-0 sm:grid-cols-3 md:grid-cols-3"
        stats={[
          { label: "Proposals opened", value: result.proposals, tone: "info", hint: "draft claims with owners" },
          { label: "Answers attached", value: result.attached, tone: "ok", hint: "to existing claims" },
          { label: "Skipped", value: result.skipped, hint: "not imported" },
        ]}
      />
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <Link href={href("/claims/proposals")} className={buttonVariants({ size: "sm" })}>
          Review proposals
          <ArrowRight aria-hidden />
        </Link>
        <Button size="sm" variant="outline" onClick={onRestart}>
          Import another
        </Button>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ screen */

export function ClaimImport() {
  const [step, setStep] = React.useState<Step>("upload");
  const [preview, setPreview] = React.useState<ImportPreview | null>(null);
  const [result, setResult] = React.useState<ImportCommitResult | null>(null);

  function restart() {
    setPreview(null);
    setResult(null);
    setStep("upload");
  }

  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Import answered questionnaires"
        description="Years of answered questionnaires become draft claims with owners and expiry, instead of a flat answer library that rots."
      />
      <ClaimsSubnav />
      <Stepper step={step} />

      {step === "upload" ? (
        <UploadStep
          onPreview={(p) => {
            setPreview(p);
            setStep("review");
          }}
        />
      ) : null}

      {step === "review" && preview ? (
        <ReviewStep
          key={preview.id}
          preview={preview}
          onRestart={restart}
          onCommitted={(r) => {
            setResult(r);
            setStep("done");
          }}
        />
      ) : null}

      {step === "done" && preview && result ? <DoneStep preview={preview} result={result} onRestart={restart} /> : null}
    </div>
  );
}
