"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, Columns3, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api, rankScore, type QuestionItem } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { DifficultyBadge, OutcomeBadge, StateBadge } from "@/components/badges";
import { EmptyState, ErrorState } from "@/components/page-header";
import { DetailSkeleton, TableSkeleton } from "@/components/skeletons";
import { SummaryStrip, type SummaryStat } from "@/components/summary-strip";
import { RouteDialog, routeSuggestions } from "@/components/route-dialog";
import { ReviewDetail, isTypingTarget } from "@/components/screens/review-detail";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export { isTypingTarget };

const COLUMN_LABEL: Record<string, string> = {
  rank: "Rank",
  customer: "Customer",
  text: "Question",
  domain: "Domain",
  difficulty: "Difficulty",
  state: "State",
  outcome: "Outcome",
  blocks_deal: "Deal",
  age_days: "Age",
};

/** Fixed widths; the question column takes what is left and truncates. */
const COLUMN_WIDTH: Record<string, string> = {
  select: "w-10",
  rank: "w-16",
  customer: "w-32",
  domain: "w-32",
  difficulty: "w-40",
  state: "w-28",
  outcome: "w-32",
  blocks_deal: "w-20",
  age_days: "w-14",
};

type Tier = "base" | "md" | "lg" | "xl" | "2xl";

/**
 * Default columns per viewport. From lg the table shares the width with the
 * detail pane, so it sheds columns the pane already shows. The Columns menu
 * still overrides within a width.
 */
const TIER_COLUMNS: Record<Tier, VisibilityState> = {
  base: { rank: false, customer: false, domain: false, difficulty: false, state: false, outcome: true, blocks_deal: true, age_days: false },
  md: { rank: true, customer: true, domain: false, difficulty: true, state: false, outcome: true, blocks_deal: true, age_days: true },
  lg: { rank: false, customer: false, domain: false, difficulty: false, state: false, outcome: false, blocks_deal: true, age_days: true },
  xl: { rank: false, customer: false, domain: false, difficulty: false, state: false, outcome: true, blocks_deal: true, age_days: true },
  "2xl": { rank: true, customer: true, domain: false, difficulty: false, state: false, outcome: true, blocks_deal: true, age_days: true },
};

const TIER_QUERIES: Array<[Tier, string]> = [
  ["2xl", "(min-width: 1536px)"],
  ["xl", "(min-width: 1280px)"],
  ["lg", "(min-width: 1024px)"],
  ["md", "(min-width: 768px)"],
];

/** null until mounted, so the first client render matches the server. */
function useTier(): Tier | null {
  const [tier, setTier] = React.useState<Tier | null>(null);
  React.useEffect(() => {
    const mqs = TIER_QUERIES.map(([t, q]) => [t, window.matchMedia(q)] as const);
    const apply = () => setTier(mqs.find(([, mq]) => mq.matches)?.[0] ?? "base");
    apply();
    for (const [, mq] of mqs) mq.addEventListener("change", apply);
    return () => {
      for (const [, mq] of mqs) mq.removeEventListener("change", apply);
    };
  }, []);
  return tier;
}

type Quick = "all" | "blocks" | "refused" | "held" | "ready";

const QUICK: Array<{ id: Quick; label: string; dot: string | null; test: (i: QuestionItem) => boolean }> = [
  { id: "all", label: "All", dot: null, test: () => true },
  { id: "blocks", label: "Blocks deal", dot: "bg-status-critical", test: (i) => i.blocks_deal },
  { id: "refused", label: "Refused", dot: "bg-status-critical", test: (i) => i.verdict?.outcome === "REFUSE" },
  { id: "held", label: "Held", dot: "bg-status-warn", test: (i) => i.verdict?.outcome === "HOLD_HUMAN" },
  { id: "ready", label: "Ready", dot: "bg-status-ok", test: (i) => i.verdict?.outcome === "ANSWER" },
];

const EDGE: Record<string, string> = {
  ANSWER: "bg-status-ok",
  HOLD_HUMAN: "bg-status-warn",
  REFUSE: "bg-status-critical",
};

function SortHeader({ label, sorted, onToggle }: { label: string; sorted: false | "asc" | "desc"; onToggle?: (e: unknown) => void }) {
  const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown;
  return (
    <button
      type="button"
      onClick={onToggle}
      className="-ml-1 inline-flex h-6 items-center gap-1 rounded-sm px-1 text-left font-medium hover:bg-muted"
      aria-label={`Sort by ${label.toLowerCase()}`}
    >
      {label}
      <Icon aria-hidden className={cn("size-3", sorted ? "text-foreground" : "text-muted-foreground")} />
    </button>
  );
}

const checkboxCls = "size-3.5 cursor-pointer rounded-sm accent-primary align-middle";

const columns: ColumnDef<QuestionItem>[] = [
  {
    id: "select",
    header: ({ table }) => (
      <input
        type="checkbox"
        className={checkboxCls}
        aria-label="Select every visible question"
        checked={table.getIsAllPageRowsSelected()}
        ref={(el) => {
          if (el) el.indeterminate = table.getIsSomePageRowsSelected();
        }}
        onChange={table.getToggleAllPageRowsSelectedHandler()}
      />
    ),
    cell: ({ row }) => (
      <>
        <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", EDGE[row.original.verdict?.outcome ?? ""] ?? "bg-border")} />
        <input
          type="checkbox"
          className={checkboxCls}
          aria-label={`Select ${row.original.customer} question ${row.original.ordinal}`}
          checked={row.getIsSelected()}
          onChange={row.getToggleSelectedHandler()}
          onClick={(e) => e.stopPropagation()}
          data-testid={`queue-select-${row.id}`}
        />
      </>
    ),
    enableSorting: false,
    enableHiding: false,
  },
  {
    id: "rank",
    accessorFn: (r) => rankScore(r),
    header: ({ column }) => <SortHeader label="Rank" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ getValue }) => <span className="font-mono text-xs tabular-nums">{String(getValue())}</span>,
    sortDescFirst: true,
  },
  {
    id: "customer",
    accessorKey: "customer",
    header: ({ column }) => <SortHeader label="Customer" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ row }) => (
      <span className="block truncate" title={row.original.customer}>
        {row.original.customer}
      </span>
    ),
  },
  {
    id: "text",
    accessorKey: "text",
    header: "Question",
    cell: ({ row }) => (
      <span className="block truncate" title={`${row.original.customer}, Q${row.original.ordinal}: ${row.original.text}`}>
        <span className="mr-1.5 font-mono text-[10px] tabular-nums text-muted-foreground">Q{row.original.ordinal}</span>
        {row.original.text}
      </span>
    ),
    enableSorting: false,
    enableHiding: false,
  },
  {
    id: "domain",
    accessorKey: "domain",
    header: ({ column }) => <SortHeader label="Domain" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ getValue }) => <span className="block truncate text-muted-foreground">{String(getValue())}</span>,
  },
  {
    id: "difficulty",
    accessorFn: (r) => r.difficulty ?? "",
    header: ({ column }) => <SortHeader label="Difficulty" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ row }) => <DifficultyBadge difficulty={row.original.difficulty} />,
  },
  {
    id: "state",
    accessorKey: "state",
    header: ({ column }) => <SortHeader label="State" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ row }) => <StateBadge state={row.original.state} />,
  },
  {
    id: "outcome",
    accessorFn: (r) => r.verdict?.outcome ?? "",
    header: ({ column }) => <SortHeader label="Outcome" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ row }) =>
      row.original.verdict ? <OutcomeBadge outcome={row.original.verdict.outcome} /> : <span className="text-xs text-muted-foreground">Not gated</span>,
  },
  {
    id: "blocks_deal",
    accessorKey: "blocks_deal",
    header: ({ column }) => <SortHeader label="Deal" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ row }) =>
      row.original.blocks_deal ? (
        <span
          className="inline-flex h-5 items-center rounded-sm border border-status-critical/40 bg-status-critical-wash px-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-status-critical"
          title="Blocks a deal"
        >
          blocks
        </span>
      ) : null,
    sortDescFirst: true,
  },
  {
    id: "age_days",
    accessorKey: "age_days",
    header: ({ column }) => <SortHeader label="Age" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ getValue }) => <span className="font-mono text-xs tabular-nums">{String(getValue())}d</span>,
    sortDescFirst: true,
  },
];

/** The queue renders inside Suspense because it reads ?item= from the URL. */
export function ReviewQueue() {
  return (
    <React.Suspense fallback={<TableSkeleton rows={8} />}>
      <Workbench />
    </React.Suspense>
  );
}

function summarise(items: QuestionItem[]): SummaryStat[] {
  const blocking = items.filter((i) => i.blocks_deal);
  const deals = new Set(blocking.map((i) => i.deal_id)).size;
  const refused = items.filter((i) => i.verdict?.outcome === "REFUSE").length;
  const held = items.filter((i) => i.verdict?.outcome === "HOLD_HUMAN").length;
  const ready = items.filter((i) => i.verdict?.outcome === "ANSWER").length;
  const oldest = items.reduce<QuestionItem | null>((a, i) => (!a || i.age_days > a.age_days ? i : a), null);
  const customers = new Set(items.map((i) => i.customer)).size;
  return [
    { label: "In queue", value: items.length, hint: `${customers} ${customers === 1 ? "customer" : "customers"}` },
    {
      label: "Blocking deals",
      value: blocking.length,
      tone: blocking.length ? "critical" : "default",
      hint: blocking.length ? `${deals} ${deals === 1 ? "deal" : "deals"} waiting` : "no deal waiting",
    },
    { label: "Refused", value: refused, tone: refused ? "critical" : "default", hint: "no claim lets it leave" },
    { label: "Held for a human", value: held, tone: held ? "warn" : "default", hint: "a person decides" },
    {
      label: "Oldest open",
      value: oldest ? `${oldest.age_days}d` : "0d",
      tone: oldest && oldest.age_days > 0 ? "warn" : "default",
      hint: oldest ? `${oldest.customer} Q${oldest.ordinal}` : undefined,
    },
    { label: "Ready to approve", value: ready, tone: ready ? "ok" : "default", hint: "claim-backed drafts" },
  ];
}

function Workbench() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { href } = useEmbed();
  const tier = useTier();
  /** The detail pane exists from lg up; below it a row opens the full page. */
  const paneOpen = tier === "lg" || tier === "xl" || tier === "2xl";
  const { data, error, loading, reload } = useAsync(() => api.reviewQueue(), []);

  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = React.useState("");
  const [quick, setQuick] = React.useState<Quick>("all");
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>(TIER_COLUMNS.base);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [paneVersion, setPaneVersion] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const [routing, setRouting] = React.useState<QuestionItem | null>(null);
  const rowRefs = React.useRef<Map<string, HTMLTableRowElement>>(new Map());
  const seeded = React.useRef(false);
  const lastIndex = React.useRef(0);

  const items = React.useMemo(() => data ?? [], [data]);
  const visible = React.useMemo(() => {
    const test = QUICK.find((q) => q.id === quick)?.test ?? (() => true);
    return items.filter(test);
  }, [items, quick]);

  const table = useReactTable({
    data: visible,
    columns,
    getRowId: (r) => r.id,
    state: { sorting, globalFilter, rowSelection, columnVisibility },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    onColumnVisibilityChange: setColumnVisibility,
    enableRowSelection: true,
    globalFilterFn: (row, _columnId, value: string) => {
      const q = String(value ?? "").trim().toLowerCase();
      if (!q) return true;
      return row.original.text.toLowerCase().includes(q) || row.original.customer.toLowerCase().includes(q);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  // Columns follow the viewport tier; the Columns menu overrides within a tier.
  React.useEffect(() => {
    if (tier) setColumnVisibility(TIER_COLUMNS[tier]);
  }, [tier]);

  // A quick filter is a new working set; a selection made in the old one does not carry.
  React.useEffect(() => {
    setRowSelection({});
  }, [quick]);

  const rows = table.getRowModel().rows;
  const suggestions = React.useMemo(() => routeSuggestions(items.map((i) => i.verdict?.route)), [items]);
  const counts = React.useMemo(() => Object.fromEntries(QUICK.map((q) => [q.id, items.filter(q.test).length])) as Record<Quick, number>, [items]);
  const stats = React.useMemo(() => summarise(items), [items]);

  // Seed the selection once (?item= wins when it is still in the queue), then keep
  // it valid: when the selected row leaves the view (approved, filtered out), take
  // the row that moved into its place.
  React.useEffect(() => {
    if (!data) return;
    if (!seeded.current) {
      seeded.current = true;
      const want = searchParams.get("item");
      if (want && rows.some((r) => r.id === want)) {
        setSelected(want);
        return;
      }
    }
    const idx = rows.findIndex((r) => r.id === selected);
    if (idx !== -1) {
      lastIndex.current = idx;
      return;
    }
    const next = rows.length ? rows[Math.min(lastIndex.current, rows.length - 1)].id : null;
    if (next !== selected) setSelected(next);
  }, [data, rows, selected, searchParams]);

  // Keep ?item= in sync so a refresh keeps the selection. Debounced so j held down
  // does not replace the URL on every row it passes.
  const userPicked = React.useRef(false);
  React.useEffect(() => {
    if (!paneOpen || !selected || !userPicked.current) return;
    if (searchParams.get("item") === selected) return;
    const t = window.setTimeout(() => {
      const sp = new URLSearchParams(searchParams.toString());
      sp.set("item", selected);
      router.replace(`${pathname}?${sp.toString()}`, { scroll: false });
    }, 200);
    return () => window.clearTimeout(t);
  }, [selected, paneOpen, pathname, router, searchParams]);

  const select = React.useCallback((id: string) => {
    userPicked.current = true;
    setSelected(id);
  }, []);

  const open = React.useCallback(
    (id: string, edit = false) => {
      router.push(href(`/review/${id}${edit ? "?edit=1" : ""}`));
    },
    [router, href],
  );

  const approve = React.useCallback(
    async (item: QuestionItem) => {
      if (busy) return;
      if (item.verdict?.outcome === "REFUSE") {
        toast.error("A refused answer cannot be approved", { description: "No claim supports it. Route it to an owner who can write one." });
        return;
      }
      setBusy(true);
      try {
        await api.approve(item.id);
        toast.success("Approved", { description: `${item.customer}, question ${item.ordinal}` });
        reload();
        setPaneVersion((v) => v + 1);
      } catch (e) {
        toast.error("Could not approve", { description: e instanceof Error ? e.message : String(e) });
      } finally {
        setBusy(false);
      }
    },
    [busy, reload],
  );

  const route = React.useCallback(
    async (item: QuestionItem, to: string, deadline: string) => {
      try {
        await api.route(item.id, to, deadline);
        toast.success(`Routed to ${to}`, { description: `Due ${deadline}` });
        reload();
        setPaneVersion((v) => v + 1);
      } catch (e) {
        toast.error("Could not route", { description: e instanceof Error ? e.message : String(e) });
        throw e;
      }
    },
    [reload],
  );

  const picked = rows.filter((r) => r.getIsSelected()).map((r) => r.original);
  const allReused = picked.length > 0 && picked.every((i) => i.difficulty === "reused");

  const bulkApprove = React.useCallback(async () => {
    if (busy || !picked.length || !picked.every((i) => i.difficulty === "reused")) return;
    setBusy(true);
    const results = await Promise.allSettled(picked.map((i) => api.approve(i.id)));
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.length - ok;
    if (failed) toast.error(`Approved ${ok} of ${results.length}`, { description: `${failed} could not be approved; they stay in the queue.` });
    else toast.success(`Approved ${ok} reused ${ok === 1 ? "answer" : "answers"}`, { description: "Each was approved verbatim against its claim." });
    setRowSelection({});
    setBusy(false);
    reload();
    setPaneVersion((v) => v + 1);
  }, [busy, picked, reload]);

  const move = React.useCallback(
    (delta: 1 | -1) => {
      if (!rows.length) return;
      const idx = rows.findIndex((r) => r.id === selected);
      const next = idx === -1 ? (delta === 1 ? 0 : rows.length - 1) : Math.min(rows.length - 1, Math.max(0, idx + delta));
      const id = rows[next].id;
      select(id);
      rowRefs.current.get(id)?.scrollIntoView({ block: "nearest" });
    },
    [rows, selected, select],
  );

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (routing || isTypingTarget(e.target)) return;
      const current = selected ? (rows.find((r) => r.id === selected) ?? null) : null;
      switch (e.key) {
        case "j":
          e.preventDefault();
          move(1);
          break;
        case "k":
          e.preventDefault();
          move(-1);
          break;
        case "x":
          if (current) {
            e.preventDefault();
            current.toggleSelected();
          }
          break;
        case "Enter":
          // Enter on a button or link belongs to that control.
          if (current && !(e.target instanceof Element && e.target.closest("button, a, summary, [role=button]"))) {
            e.preventDefault();
            open(current.id);
          }
          break;
      }
      // With the pane open, a, e and r belong to the pane, which acts on the same item.
      if (paneOpen || !current) return;
      switch (e.key) {
        case "a":
          e.preventDefault();
          void approve(current.original);
          break;
        case "e":
          e.preventDefault();
          open(current.id, true);
          break;
        case "r":
          e.preventDefault();
          setRouting(current.original);
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, selected, routing, paneOpen, move, open, approve]);

  const onPaneChange = React.useCallback(() => reload(), [reload]);

  if (loading && !data) return <TableSkeleton rows={8} />;
  if (error) return <ErrorState error={error} />;

  const position = rows.findIndex((r) => r.id === selected);

  return (
    <div className="space-y-4" data-testid="review-queue">
      <SummaryStrip stats={stats} />

      {items.length === 0 ? (
        <EmptyState title="Nothing waiting for review" body="Every drafted answer has been approved, routed or refused." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start xl:grid-cols-[minmax(0,8fr)_minmax(0,7fr)]">
          <div className="min-w-0 space-y-2.5">
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Quick filters">
              {QUICK.map((q) => {
                const active = quick === q.id;
                return (
                  <button
                    key={q.id}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setQuick(q.id)}
                    data-testid={`quick-${q.id}`}
                    className={cn(
                      "inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors",
                      active ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {q.dot ? <span aria-hidden className={cn("size-1.5 rounded-full", q.dot)} /> : null}
                    {q.label}
                    <span className={cn("font-mono text-[11px] tabular-nums", active ? "opacity-90" : "text-foreground/70")}>{counts[q.id]}</span>
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="search"
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
                placeholder="Filter by question or customer"
                aria-label="Filter by question or customer"
                className="h-8 max-w-xs"
                data-testid="queue-filter"
              />
              <span className="eyebrow tabular-nums" aria-live="polite">
                {rows.length} of {items.length}
              </span>
              <DropdownMenu>
                <DropdownMenuTrigger render={<Button variant="outline" size="sm" className="ml-auto" aria-label="Choose columns" />}>
                  <Columns3 aria-hidden />
                  Columns
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-44">
                  <DropdownMenuLabel>Show columns</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {table
                    .getAllLeafColumns()
                    .filter((c) => c.getCanHide())
                    .map((c) => (
                      <DropdownMenuCheckboxItem key={c.id} checked={c.getIsVisible()} onCheckedChange={(v) => c.toggleVisibility(Boolean(v))}>
                        {COLUMN_LABEL[c.id] ?? c.id}
                      </DropdownMenuCheckboxItem>
                    ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {picked.length ? (
              <div className="flex min-h-9 flex-wrap items-center gap-3 rounded-md border bg-muted/50 px-3 py-1.5 text-sm" data-testid="bulk-bar" aria-live="polite">
                <span className="font-medium tabular-nums">{picked.length} selected</span>
                {allReused ? (
                  <Button size="sm" onClick={() => void bulkApprove()} disabled={busy} data-testid="bulk-approve">
                    {busy ? "Approving" : `Approve ${picked.length} reused`}
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground" data-testid="bulk-unavailable">
                    Bulk approve is only for reused answers.
                  </span>
                )}
                <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setRowSelection({})}>
                  Clear
                </Button>
              </div>
            ) : null}

            <div className="overflow-x-auto rounded-md border bg-card md:max-h-[calc(100dvh-17rem)] md:overflow-y-auto">
              <table aria-label="Review queue" className="w-full min-w-[34rem] table-fixed caption-bottom text-sm md:min-w-[56rem] lg:min-w-0">
                <TableHeader className="[&_tr]:border-b-0">
                  {table.getHeaderGroups().map((hg) => (
                    <TableRow key={hg.id} className="hover:bg-transparent">
                      {hg.headers.map((h) => {
                        const sorted = h.column.getIsSorted();
                        return (
                          <TableHead
                            key={h.id}
                            aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                            className={cn(
                              "sticky top-0 z-10 h-8 bg-card px-2 text-xs text-muted-foreground shadow-[inset_0_-1px_0_var(--border)]",
                              h.column.id === "select" && "pl-3",
                              COLUMN_WIDTH[h.column.id],
                            )}
                          >
                            {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                          </TableHead>
                        );
                      })}
                    </TableRow>
                  ))}
                </TableHeader>
                <TableBody>
                  {rows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={table.getVisibleLeafColumns().length} className="py-8 text-center text-muted-foreground">
                        No question matches that filter.
                      </TableCell>
                    </TableRow>
                  ) : (
                    rows.map((row) => {
                      const active = row.id === selected;
                      return (
                        <TableRow
                          key={row.id}
                          ref={(el) => {
                            if (el) rowRefs.current.set(row.id, el);
                            else rowRefs.current.delete(row.id);
                          }}
                          tabIndex={0}
                          data-highlighted={active || undefined}
                          data-outcome={row.original.verdict?.outcome}
                          data-testid={`queue-row-${row.id}`}
                          aria-selected={active}
                          className={cn(
                            "h-9 cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                            active && "bg-accent shadow-[inset_0_0_0_1px_var(--ring)] hover:bg-accent",
                            row.getIsSelected() && !active && "bg-muted/40",
                          )}
                          onClick={() => (paneOpen ? select(row.id) : open(row.id))}
                          onFocus={() => select(row.id)}
                        >
                          {row.getVisibleCells().map((cell) => (
                            <TableCell key={cell.id} className={cn("overflow-hidden px-2 py-0", cell.column.id === "select" && "relative pl-3")}>
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </TableCell>
                          ))}
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </table>
            </div>

            <ul className="hidden flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground md:flex" aria-label="Keyboard shortcuts">
              <li className="flex items-center gap-1">
                <Kbd>j</Kbd>
                <Kbd>k</Kbd>
                <span>move</span>
              </li>
              <li className="flex items-center gap-1">
                <Kbd>Enter</Kbd>
                <span>open full page</span>
              </li>
              <li className="flex items-center gap-1">
                <Kbd>x</Kbd>
                <span>select</span>
              </li>
              <li className="flex items-center gap-1">
                <Kbd>a</Kbd>
                <span>approve</span>
              </li>
              <li className="flex items-center gap-1">
                <Kbd>e</Kbd>
                <span>edit</span>
              </li>
              <li className="flex items-center gap-1">
                <Kbd>r</Kbd>
                <span>route</span>
              </li>
            </ul>
          </div>

          <aside
            aria-label="Selected question"
            className="hidden min-w-0 rounded-md border bg-card lg:sticky lg:top-28 lg:block lg:max-h-[calc(100dvh-8rem)] lg:overflow-y-auto"
            data-testid="review-pane"
          >
            <div className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b bg-card px-4 py-2">
              <span className="eyebrow tabular-nums">{position === -1 ? "Nothing selected" : `${position + 1} of ${rows.length}`}</span>
              {selected ? (
                <Link
                  href={href(`/review/${selected}`)}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                  data-testid="pane-open-full"
                >
                  <ExternalLink aria-hidden className="size-3.5" />
                  Open full page
                  <Kbd>Enter</Kbd>
                </Link>
              ) : null}
            </div>
            <div className="p-4">
              {paneOpen && selected ? (
                <ReviewDetail key={`${selected}:${paneVersion}`} id={selected} embedded onChange={onPaneChange} />
              ) : tier === null ? (
                <DetailSkeleton />
              ) : (
                <p className="text-sm text-muted-foreground">Pick a question to review it here.</p>
              )}
            </div>
          </aside>
        </div>
      )}

      <RouteDialog
        open={routing !== null}
        onOpenChange={(o) => {
          if (!o) setRouting(null);
        }}
        suggestions={suggestions}
        subject={routing ? `${routing.customer}, question ${routing.ordinal}` : undefined}
        onSubmit={(to, deadline) => (routing ? route(routing, to, deadline) : undefined)}
      />
    </div>
  );
}
