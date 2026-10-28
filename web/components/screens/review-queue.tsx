"use client";

import * as React from "react";
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
import { ArrowDown, ArrowUp, ArrowUpDown, Columns3 } from "lucide-react";
import { toast } from "sonner";
import { api, rankScore, type QuestionItem } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { DifficultyBadge, OutcomeBadge, StateBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/page-header";
import { RouteDialog, routeSuggestions } from "@/components/route-dialog";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

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

/** Columns that only fit from md up; the matchMedia effect flips them. */
const WIDE_ONLY = ["domain", "rank", "age_days"] as const;

/** True when a keystroke belongs to a field, not to the page. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return target.closest("[role=dialog], [role=menu], [role=listbox], [role=combobox], [contenteditable=true]") !== null;
}

function SortHeader({ label, sorted, onToggle }: { label: string; sorted: false | "asc" | "desc"; onToggle?: (e: unknown) => void }) {
  const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown;
  return (
    <button
      type="button"
      onClick={onToggle}
      className="-ml-1 inline-flex h-7 items-center gap-1 rounded-sm px-1 text-left font-medium hover:bg-muted"
      aria-label={`Sort by ${label.toLowerCase()}`}
    >
      {label}
      <Icon aria-hidden className={cn("size-3.5", sorted ? "text-foreground" : "text-muted-foreground")} />
    </button>
  );
}

const columns: ColumnDef<QuestionItem>[] = [
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
      <span className="block max-w-[10rem] truncate" title={row.original.customer}>
        {row.original.customer}
      </span>
    ),
  },
  {
    id: "text",
    accessorKey: "text",
    header: "Question",
    cell: ({ row }) => (
      <span className="line-clamp-2 min-w-[14rem] max-w-[34rem] whitespace-normal leading-snug">
        <span className="mr-1.5 font-mono text-[10px] text-muted-foreground">Q{row.original.ordinal}</span>
        {row.original.text}
      </span>
    ),
    enableSorting: false,
  },
  {
    id: "domain",
    accessorKey: "domain",
    header: ({ column }) => <SortHeader label="Domain" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ getValue }) => <span className="text-muted-foreground">{String(getValue())}</span>,
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
    cell: ({ row }) => (row.original.verdict ? <OutcomeBadge outcome={row.original.verdict.outcome} /> : <span className="text-muted-foreground">Not gated</span>),
  },
  {
    id: "blocks_deal",
    accessorKey: "blocks_deal",
    header: ({ column }) => <SortHeader label="Deal" sorted={column.getIsSorted()} onToggle={column.getToggleSortingHandler()} />,
    cell: ({ row }) =>
      row.original.blocks_deal ? (
        <span className="inline-flex h-5 items-center rounded-sm border border-status-critical/40 bg-status-critical-wash px-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-status-critical">
          blocks deal
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

export function ReviewQueue() {
  const router = useRouter();
  const { href } = useEmbed();
  const { data, error, loading, reload } = useAsync(() => api.reviewQueue(), []);

  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = React.useState("");
  const [highlighted, setHighlighted] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [routing, setRouting] = React.useState<QuestionItem | null>(null);
  const rowRefs = React.useRef<Map<string, HTMLTableRowElement>>(new Map());

  const items = React.useMemo(() => data ?? [], [data]);

  const table = useReactTable({
    data: items,
    columns,
    getRowId: (r) => r.id,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: (row, _columnId, value: string) => {
      const q = String(value ?? "").trim().toLowerCase();
      if (!q) return true;
      return row.original.text.toLowerCase().includes(q) || row.original.customer.toLowerCase().includes(q);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    initialState: {
      columnVisibility: { domain: false, rank: false, age_days: false },
    },
  });

  // Wide-only columns follow the viewport; the dropdown still overrides within a width.
  React.useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const apply = () => {
      table.setColumnVisibility((v) => {
        const next = { ...v };
        for (const id of WIDE_ONLY) next[id] = mq.matches;
        return next;
      });
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [table]);

  const rows = table.getRowModel().rows;
  const suggestions = React.useMemo(() => routeSuggestions(items.map((i) => i.verdict?.route)), [items]);

  const open = React.useCallback(
    (id: string, edit = false) => {
      router.push(href(`/review/${id}${edit ? "?edit=1" : ""}`));
    },
    [router, href],
  );

  const approve = React.useCallback(
    async (item: QuestionItem) => {
      if (busy) return;
      setBusy(true);
      try {
        await api.approve(item.id);
        toast.success("Approved", { description: `${item.customer}, question ${item.ordinal}` });
        reload();
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
      } catch (e) {
        toast.error("Could not route", { description: e instanceof Error ? e.message : String(e) });
        throw e;
      }
    },
    [reload],
  );

  const move = React.useCallback(
    (delta: 1 | -1) => {
      if (!rows.length) return;
      const idx = rows.findIndex((r) => r.id === highlighted);
      const next = idx === -1 ? (delta === 1 ? 0 : rows.length - 1) : Math.min(rows.length - 1, Math.max(0, idx + delta));
      const id = rows[next].id;
      setHighlighted(id);
      rowRefs.current.get(id)?.scrollIntoView({ block: "nearest" });
    },
    [rows, highlighted],
  );

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (routing || isTypingTarget(e.target)) return;
      const current = highlighted ? (rows.find((r) => r.id === highlighted)?.original ?? null) : null;
      switch (e.key) {
        case "j":
          e.preventDefault();
          move(1);
          break;
        case "k":
          e.preventDefault();
          move(-1);
          break;
        case "Enter":
          if (current) {
            e.preventDefault();
            open(current.id);
          }
          break;
        case "a":
          if (current) {
            e.preventDefault();
            void approve(current);
          }
          break;
        case "e":
          if (current) {
            e.preventDefault();
            open(current.id, true);
          }
          break;
        case "r":
          if (current) {
            e.preventDefault();
            setRouting(current);
          }
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, highlighted, routing, move, open, approve]);

  if (loading && !data) return <LoadingState label="Loading the queue" />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-3" data-testid="review-queue">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="search"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder="Filter by question or customer"
          aria-label="Filter by question or customer"
          className="max-w-xs"
          data-testid="queue-filter"
        />
        <span className="eyebrow" aria-live="polite">
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

      {items.length === 0 ? (
        <EmptyState title="Nothing waiting for review" body="Every drafted answer has been approved, routed or refused." />
      ) : (
        <div className="rounded-md border">
          <Table aria-label="Review queue">
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id} className="hover:bg-transparent">
                  {hg.headers.map((h) => {
                    const sorted = h.column.getIsSorted();
                    return (
                      <TableHead key={h.id} aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined} className="text-xs">
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
                  const active = row.id === highlighted;
                  return (
                    <TableRow
                      key={row.id}
                      ref={(el) => {
                        if (el) rowRefs.current.set(row.id, el);
                        else rowRefs.current.delete(row.id);
                      }}
                      tabIndex={0}
                      data-highlighted={active || undefined}
                      data-testid={`queue-row-${row.id}`}
                      aria-selected={active}
                      className={cn("cursor-pointer outline-none", active && "bg-muted/60 ring-2 ring-inset ring-ring")}
                      onClick={() => open(row.id)}
                      onFocus={() => setHighlighted(row.id)}
                      onMouseEnter={() => setHighlighted(row.id)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id} className="align-top">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>
      )}

      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Keyboard shortcuts">
        <li className="flex items-center gap-1">
          <Kbd>j</Kbd>
          <Kbd>k</Kbd>
          <span>move</span>
        </li>
        <li className="flex items-center gap-1">
          <Kbd>Enter</Kbd>
          <span>open</span>
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
