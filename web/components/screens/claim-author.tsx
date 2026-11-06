"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowRight, FileText, Quote, RotateCcw } from "lucide-react";
import { api, type Audience, type AuthorInput, type AuthorRun, type Product } from "@/lib/api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { SummaryStrip } from "@/components/summary-strip";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";
import { ExceptionChip, FlagChip } from "@/components/badges";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/* ------------------------------------------------------------------ */
/* Author: a policy or a docs page becomes draft claims, one fact each, */
/* every one quoting the exact span it came from. Nothing here is      */
/* verified; each draft opens as a proposal a second person approves.  */
/* ------------------------------------------------------------------ */

const ACCEPT = [".pdf", ".docx", ".md", ".txt"] as const;

const PRODUCTS: { value: Product; label: string }[] = [
  { value: "catalog", label: "Catalog" },
  { value: "ai-features", label: "AI features" },
  { value: "mcp", label: "MCP server" },
];

const AUDIENCES: { value: Audience; label: string }[] = [
  { value: "public", label: "Public" },
  { value: "nda", label: "Under NDA" },
  { value: "internal", label: "Internal" },
];

const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$/;
const VERSION_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/;

export function ClaimAuthor() {
  const [run, setRun] = React.useState<AuthorRun | null>(null);
  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Draft claims from a source"
        description="A policy, a standard or a docs page becomes draft claims, one fact each, every one quoting the sentence it came from. A second person approves each draft before it can answer anything."
      />
      <ClaimsSubnav />
      {run ? <Result run={run} onRestart={() => setRun(null)} /> : <SourceForm onDone={setRun} />}
    </div>
  );
}

function SourceForm({ onDone }: { onDone: (r: AuthorRun) => void }) {
  const [sourceId, setSourceId] = React.useState("");
  const [version, setVersion] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [owner, setOwner] = React.useState("");
  const [audience, setAudience] = React.useState<Audience>("nda");
  const [products, setProducts] = React.useState<Product[]>([]);
  const [text, setText] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState(false);

  const idOk = ID_RE.test(sourceId);
  const versionOk = VERSION_RE.test(version);
  const hasSource = Boolean(file) || text.trim().length > 0;
  const canSubmit = idOk && versionOk && hasSource && !busy;

  function pickFile(f: File | null) {
    if (f && !ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext))) {
      toast.error(`${f.name} is not a supported file. Use ${ACCEPT.join(", ")}.`);
      return;
    }
    setFile(f);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    const input: AuthorInput = { source_id: sourceId, version, title: title.trim(), url: url.trim(), products, owner: owner.trim(), audience };
    try {
      onDone(await api.authorClaims(input, file ? { file } : { text }));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]" aria-busy={busy} data-testid="author-form">
      <div className="flex min-w-0 flex-col gap-3 rounded-md border bg-card p-3">
        <label htmlFor="author-text" className="eyebrow">
          Source text
        </label>
        <Textarea
          id="author-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste a policy section or a docs page. Markdown is fine."
          className="min-h-72 font-mono text-[13px] leading-relaxed"
          disabled={busy || Boolean(file)}
        />
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>or a file</span>
          <label className={cn(buttonVariants({ variant: "outline", size: "sm" }), "cursor-pointer")}>
            <FileText className="size-3.5" aria-hidden />
            {file ? file.name : "Choose pdf, docx, md or txt"}
            <input
              type="file"
              accept={ACCEPT.join(",")}
              className="sr-only"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
              disabled={busy}
              data-testid="author-file"
            />
          </label>
          {file ? (
            <button type="button" className="underline-offset-2 hover:underline" onClick={() => setFile(null)}>
              use pasted text instead
            </button>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-md border bg-card p-3">
        <Field id="author-source" label="Source id" hint={sourceId && !idOk ? "Letters, digits and ._:/- only" : "e.g. POL-ENC-001 or atlan-docs/mcp-security"}>
          <Input id="author-source" value={sourceId} onChange={(e) => setSourceId(e.target.value)} autoComplete="off" disabled={busy} required />
        </Field>
        <Field id="author-version" label="Version" hint={version && !versionOk ? "Letters, digits and ._- only" : "the document's version or date"}>
          <Input id="author-version" value={version} onChange={(e) => setVersion(e.target.value)} autoComplete="off" disabled={busy} required />
        </Field>
        <Field id="author-title" label="Title">
          <Input id="author-title" value={title} onChange={(e) => setTitle(e.target.value)} disabled={busy} />
        </Field>
        <Field id="author-url" label="Link">
          <Input id="author-url" value={url} onChange={(e) => setUrl(e.target.value)} type="url" disabled={busy} />
        </Field>
        <fieldset className="grid gap-1.5">
          <legend className="eyebrow mb-1">About</legend>
          <div className="flex flex-wrap gap-3">
            {PRODUCTS.map((p) => (
              <label key={p.value} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={products.includes(p.value)}
                  onChange={(e) => setProducts((cur) => (e.target.checked ? [...cur, p.value] : cur.filter((x) => x !== p.value)))}
                  disabled={busy}
                />
                {p.label}
              </label>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground">Used when a sentence names no product itself.</p>
        </fieldset>
        <Field id="author-owner" label="Owner" hint="a person's address; defaults to you">
          <Input id="author-owner" value={owner} onChange={(e) => setOwner(e.target.value)} type="email" autoComplete="off" disabled={busy} />
        </Field>
        <div className="grid gap-1.5">
          <span id="author-audience-label" className="eyebrow">
            Audience
          </span>
          <Select value={audience} onValueChange={(v) => setAudience((v as Audience | null) ?? "nda")} disabled={busy}>
            <SelectTrigger className="w-full" aria-labelledby="author-audience-label">
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
        </div>
        <p className="rounded-sm border-l-2 border-status-info bg-status-info-wash px-2.5 py-2 text-xs leading-relaxed text-muted-foreground">
          What a document says is not proof it is true. Every draft is a proposal; certificates are never drafted from text.
        </p>
        <Button type="submit" disabled={!canSubmit} className="mt-auto w-full">
          {busy ? "Reading the source" : "Draft claims"}
        </Button>
      </div>
    </form>
  );
}

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="eyebrow">
        {label}
      </label>
      {children}
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function Result({ run, onRestart }: { run: AuthorRun; onRestart: () => void }) {
  const { href } = useEmbed();
  return (
    <div className="space-y-5" data-testid="author-result">
      <SummaryStrip
        stats={[
          { label: "Drafted", value: run.proposals.length, hint: "opened as proposals", tone: run.proposals.length ? "ok" : "default" },
          { label: "Skipped", value: run.skipped.length, hint: "each with its reason" },
          { label: "Version", value: run.version, hint: run.source_id },
          { label: "Extractor", value: run.model_id, hint: "deterministic unless a model is configured" },
        ]}
        className="sm:grid-cols-4 md:grid-cols-4"
      />

      <div className="flex flex-wrap gap-2">
        <Link href={href("/claims/proposals")} className={buttonVariants({ size: "sm" })}>
          Review the proposals <ArrowRight className="size-3.5" aria-hidden />
        </Link>
        <Button variant="outline" size="sm" onClick={onRestart}>
          <RotateCcw className="size-3.5" aria-hidden /> Draft from another source
        </Button>
      </div>

      <section aria-labelledby="author-drafts" className="space-y-2">
        <h2 id="author-drafts" className="eyebrow">
          Drafts
        </h2>
        {run.proposals.length ? (
          <ol className="space-y-2">
            {run.proposals.map(({ proposal_id, claim_id, draft }) => (
              <li key={proposal_id} className="rounded-md border bg-card p-3" data-testid="author-draft">
                <p className="text-sm leading-relaxed">{draft.statement}</p>
                <blockquote className="mt-2 flex gap-2 border-l-2 border-border pl-2.5 text-xs text-muted-foreground">
                  <Quote className="mt-0.5 size-3 shrink-0" aria-hidden />
                  <span>
                    {draft.span.text}
                    <span className="ml-1.5 font-mono text-[10px] opacity-70">
                      [{draft.span.start}:{draft.span.end}]
                    </span>
                  </span>
                </blockquote>
                {draft.exceptions.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {draft.exceptions.map((e) => (
                      <ExceptionChip key={e} text={e} />
                    ))}
                  </div>
                ) : null}
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {[...draft.products, ...draft.data_classes].map((p) => (
                    <FlagChip key={p} flag={p} />
                  ))}
                  <span className="ml-auto font-mono text-[10px] text-muted-foreground">{claim_id}</span>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">No sentence in this source reads as a present-tense fact.</p>
        )}
      </section>

      {run.skipped.length ? (
        <details className="rounded-md border bg-card" data-testid="author-skipped">
          <summary className="cursor-pointer px-3 py-2 text-sm">Skipped sentences and why ({run.skipped.length})</summary>
          <ul className="divide-y border-t text-xs">
            {run.skipped.map((s, i) => (
              <li key={`${i}-${s.text}`} className="grid gap-0.5 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_16rem] sm:gap-4">
                <span className="text-muted-foreground">{s.text || "(the rest of the source)"}</span>
                <span>{s.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
