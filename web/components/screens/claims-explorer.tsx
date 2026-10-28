"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { api, type Claim, type ClaimStatus } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, PageHeader } from "@/components/page-header";
import { TableSkeleton } from "@/components/skeletons";
import { SummaryStrip, type SummaryStat } from "@/components/summary-strip";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";
import { Input } from "@/components/ui/input";
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const STATUS_TONE: Record<ClaimStatus, string> = {
  verified: "text-status-ok",
  draft: "text-status-warn",
  deprecated: "text-muted-foreground",
};

const DAY = 86_400_000;

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function daysUntil(iso: string): number {
  return Math.round((new Date(iso).getTime() - Date.now()) / DAY);
}

function freshnessTone(d: number): string {
  if (d < 0) return "text-status-critical";
  if (d < 30) return "text-status-warn";
  return "text-foreground";
}

type Lens = "all" | "verified" | "draft" | "expiring" | "expired" | "exceptions";

const LENSES: { id: Lens; label: string }[] = [
  { id: "all", label: "All" },
  { id: "verified", label: "Verified" },
  { id: "draft", label: "Drafts" },
  { id: "expiring", label: "Expiring" },
  { id: "expired", label: "Expired" },
  { id: "exceptions", label: "With exceptions" },
];

function inLens(c: Claim, lens: Lens): boolean {
  const d = daysUntil(c.valid_until);
  switch (lens) {
    case "all":
      return true;
    case "verified":
      return c.status === "verified";
    case "draft":
      return c.status === "draft";
    case "expiring":
      return d >= 0 && d < 30;
    case "expired":
      return d < 0;
    case "exceptions":
      return c.exceptions.length > 0;
  }
}

/* Cell padding and widths live here so the column defs stay about content. */
const CELL_CLASS: Record<string, string> = {
  id: "w-[1%]",
  statement: "w-full max-w-0",
  owner: "max-w-[10rem]",
  exceptions: "text-right",
  evidence: "text-right",
  approved_answers: "text-right",
};

const HEAD = "sticky top-0 z-10 h-8 bg-card px-3 text-[11px] font-medium text-muted-foreground shadow-[inset_0_-1px_0_var(--border)]";

function buildColumns(href: (path: string) => string): ColumnDef<Claim>[] {
  return [
    {
      accessorKey: "id",
      header: "ID",
      cell: ({ getValue }) => <span className="font-mono text-[11px] text-muted-foreground">{getValue<string>()}</span>,
    },
    {
      accessorKey: "statement",
      header: "Statement",
      cell: ({ row, getValue }) => (
        <Link
          href={href(`/claims/${row.original.id}`)}
          tabIndex={-1}
          onClick={(e) => e.stopPropagation()}
          title={getValue<string>()}
          className="block truncate hover:underline"
        >
          {getValue<string>()}
        </Link>
      ),
    },
    {
      accessorKey: "owner",
      header: "Owner",
      cell: ({ row, getValue }) => (
        <span className="block truncate text-xs" title={row.original.owner_email}>
          {getValue<string>()}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ getValue }) => {
        const s = getValue<ClaimStatus>();
        return (
          <span className={cn("inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-wider before:size-1.5 before:bg-current before:content-['']", STATUS_TONE[s])}>
            {s}
          </span>
        );
      },
    },
    {
      accessorKey: "audience",
      header: "Audience",
      cell: ({ getValue }) => <span className="eyebrow">{getValue<string>()}</span>,
    },
    {
      id: "exceptions",
      accessorFn: (c) => c.exceptions.length,
      header: "Exc.",
      cell: ({ getValue }) => {
        const n = getValue<number>();
        return n === 0 ? <span className="text-muted-foreground/60">0</span> : <span className="text-status-warn">{n}</span>;
      },
    },
    {
      id: "evidence",
      accessorFn: (c) => c.evidence.length,
      header: "Evid.",
      cell: ({ getValue }) => <span>{getValue<number>()}</span>,
    },
    {
      accessorKey: "valid_until",
      header: "Valid until",
      cell: ({ getValue }) => {
        const iso = getValue<string>();
        const d = daysUntil(iso);
        return (
          <span className={cn("inline-flex items-baseline gap-2 font-mono text-[11px]", freshnessTone(d))}>
            <span>{fmtDate(iso)}</span>
            <span className={cn("text-[10.5px]", d >= 30 && "text-muted-foreground")}>{d < 0 ? `${-d} d over` : `${d} d`}</span>
          </span>
        );
      },
    },
    {
      accessorKey: "approved_answers",
      header: "Answers",
      cell: ({ getValue }) => <span className="font-mono text-xs">{getValue<number>()}</span>,
    },
  ];
}

function claimStats(data: Claim[]): SummaryStat[] {
  const days = data.map((c) => daysUntil(c.valid_until));
  const expired = days.filter((d) => d < 0).length;
  const soon = days.filter((d) => d >= 0 && d < 30).length;
  const exceptions = data.reduce((n, c) => n + c.exceptions.length, 0);
  const withExceptions = data.filter((c) => c.exceptions.length > 0).length;
  const verified = data.filter((c) => c.status === "verified").length;
  const drafts = data.filter((c) => c.status === "draft").length;
  return [
    { label: "Claims", value: data.length, hint: `${data.reduce((n, c) => n + c.approved_answers, 0)} answers rest on them` },
    { label: "Verified", value: verified, tone: "ok", hint: `${Math.round((verified / (data.length || 1)) * 100)}% of the store` },
    { label: "Drafts", value: drafts, tone: drafts ? "warn" : "default", hint: "cannot support an answer yet" },
    { label: "Expired", value: expired, tone: expired ? "critical" : "default", hint: "answers citing them are held" },
    { label: "Expiring in 30 d", value: soon, tone: soon ? "warn" : "default", hint: "owner must re-verify" },
    { label: "Exceptions carried", value: exceptions, hint: `across ${withExceptions} claims` },
  ];
}

export function ClaimsExplorer() {
  const router = useRouter();
  const { href } = useEmbed();
  const { data, error, loading } = useAsync(() => api.listClaims(), []);
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [filter, setFilter] = React.useState("");
  const [lens, setLens] = React.useState<Lens>("all");
  const columns = React.useMemo(() => buildColumns(href), [href]);

  const lensed = React.useMemo(() => (data ?? []).filter((c) => inLens(c, lens)), [data, lens]);
  const lensCounts = React.useMemo(() => {
    const out = {} as Record<Lens, number>;
    for (const l of LENSES) out[l.id] = (data ?? []).filter((c) => inLens(c, l.id)).length;
    return out;
  }, [data]);

  const table = useReactTable({
    data: lensed,
    columns,
    state: { sorting, globalFilter: filter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFilter,
    globalFilterFn: (row, _columnId, value: string) => {
      const needle = value.trim().toLowerCase();
      if (!needle) return true;
      const c = row.original;
      return (
        c.statement.toLowerCase().includes(needle) ||
        c.owner.toLowerCase().includes(needle) ||
        c.id.toLowerCase().includes(needle)
      );
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const go = (id: string) => router.push(href(`/claims/${id}`));
  const rows = table.getRowModel().rows;
  const stats = React.useMemo(() => (data ? claimStats(data) : null), [data]);

  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Claim explorer"
        description="Every claim the gate can cite. An answer only ships when a verified, in-date claim covers it."
      />
      <ClaimsSubnav />

      {loading && !data ? <TableSkeleton rows={9} /> : null}
      {error ? <ErrorState error={error} /> : null}

      {stats ? <SummaryStrip stats={stats} className="mb-4" /> : null}

      {data ? (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <div className="relative w-full max-w-xs">
              <label htmlFor="claims-filter" className="sr-only">
                Filter by statement, owner or id
              </label>
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                id="claims-filter"
                type="search"
                placeholder="Filter by statement, owner or id"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="h-7 pl-8 text-[13px]"
              />
            </div>
            <div role="group" aria-label="Show claims" className="inline-flex flex-wrap rounded-md border bg-card p-0.5">
              {LENSES.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  aria-pressed={lens === l.id}
                  onClick={() => setLens(l.id)}
                  className={cn(
                    "inline-flex h-6 items-center gap-1.5 rounded-[3px] px-2 text-xs transition-colors",
                    lens === l.id ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {l.label}
                  <span
                    className={cn(
                      "font-mono text-[10.5px] tabular-nums",
                      l.id === "expired" && lensCounts.expired > 0 && "text-status-critical",
                      l.id === "expiring" && lensCounts.expiring > 0 && "text-status-warn",
                    )}
                  >
                    {lensCounts[l.id]}
                  </span>
                </button>
              ))}
            </div>
            <p className="ml-auto font-mono text-[11px] text-muted-foreground tabular-nums" aria-live="polite">
              {rows.length} of {data.length} claims
            </p>
          </div>

          {rows.length === 0 ? (
            <EmptyState title="No claims match" body="Try a different word from the statement or the owner's name, or another lens." />
          ) : (
            <div className="max-h-[70vh] overflow-auto rounded-md border bg-card">
              <table data-slot="table" className="w-full min-w-[980px] text-[13px] tabular-nums">
                <TableHeader className="[&_tr]:border-b-0">
                  {table.getHeaderGroups().map((hg) => (
                    <TableRow key={hg.id} className="hover:bg-transparent">
                      {hg.headers.map((h) => {
                        const sorted = h.column.getIsSorted();
                        const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown;
                        const right = CELL_CLASS[h.column.id]?.includes("text-right");
                        return (
                          <TableHead
                            key={h.id}
                            scope="col"
                            className={cn(HEAD, right && "text-right")}
                            aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
                          >
                            <button
                              type="button"
                              onClick={h.column.getToggleSortingHandler()}
                              className="inline-flex items-center gap-1 rounded-sm hover:text-foreground"
                            >
                              {flexRender(h.column.columnDef.header, h.getContext())}
                              <Icon className={cn("size-3", sorted ? "opacity-100" : "opacity-30")} aria-hidden />
                            </button>
                          </TableHead>
                        );
                      })}
                    </TableRow>
                  ))}
                </TableHeader>
                <TableBody>
                  {rows.map((row) => {
                    const d = daysUntil(row.original.valid_until);
                    return (
                      <TableRow
                        key={row.id}
                        tabIndex={0}
                        onClick={() => go(row.original.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            go(row.original.id);
                          }
                        }}
                        className={cn(
                          "cursor-pointer focus-visible:bg-muted/50 focus-visible:outline-none",
                          d < 0 && "bg-status-critical-wash/40",
                        )}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <TableCell key={cell.id} className={cn("h-9 px-3 py-0", CELL_CLASS[cell.column.id])}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </TableCell>
                        ))}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
