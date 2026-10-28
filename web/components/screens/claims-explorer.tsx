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
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { api, type Claim, type ClaimStatus } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { cn } from "@/lib/utils";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from "@/components/page-header";
import { ClaimsSubnav } from "@/components/screens/claims-subnav";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const STATUS_TONE: Record<ClaimStatus, string> = {
  verified: "text-status-ok",
  draft: "text-status-warn",
  deprecated: "text-muted-foreground",
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function daysUntil(iso: string): number {
  return Math.round((new Date(iso).getTime() - Date.now()) / 86_400_000);
}

function freshnessTone(iso: string): string {
  const d = daysUntil(iso);
  if (d < 0) return "text-status-critical";
  if (d < 30) return "text-status-warn";
  return "text-foreground";
}

function buildColumns(href: (path: string) => string): ColumnDef<Claim>[] {
  return [
    {
      accessorKey: "statement",
      header: "Statement",
      cell: ({ row, getValue }) => (
        <Link
          href={href(`/claims/${row.original.id}`)}
          tabIndex={-1}
          onClick={(e) => e.stopPropagation()}
          className="block max-w-[60ch] whitespace-normal leading-snug hover:underline"
        >
          {getValue<string>()}
        </Link>
      ),
    },
    {
      accessorKey: "owner",
      header: "Owner",
      cell: ({ getValue }) => (
        <span className="whitespace-normal">{getValue<string>()}</span>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ getValue }) => {
        const s = getValue<ClaimStatus>();
        return (
          <span
            className={cn(
              "font-mono text-[11px] uppercase tracking-wider",
              STATUS_TONE[s],
            )}
          >
            {s}
          </span>
        );
      },
    },
    {
      accessorKey: "audience",
      header: "Audience",
      cell: ({ getValue }) => (
        <span className="eyebrow">{getValue<string>()}</span>
      ),
    },
    {
      id: "exceptions",
      accessorFn: (c) => c.exceptions.length,
      header: "Exceptions",
      cell: ({ getValue }) => {
        const n = getValue<number>();
        return n === 0 ? (
          <span className="text-muted-foreground">none</span>
        ) : (
          <span className="text-status-warn">{n}</span>
        );
      },
    },
    {
      id: "evidence",
      accessorFn: (c) => c.evidence.length,
      header: "Evidence",
      cell: ({ getValue }) => <span>{getValue<number>()}</span>,
    },
    {
      accessorKey: "valid_until",
      header: "Valid until",
      cell: ({ getValue }) => {
        const iso = getValue<string>();
        const d = daysUntil(iso);
        const hint =
          d < 0 ? `expired ${-d} d ago` : d < 30 ? `${d} d left` : null;
        return (
          <span className={cn("font-mono text-xs", freshnessTone(iso))}>
            {fmtDate(iso)}
            {hint ? <span className="ml-1.5 opacity-80">({hint})</span> : null}
          </span>
        );
      },
    },
    {
      accessorKey: "approved_answers",
      header: "Approved answers",
      cell: ({ getValue }) => (
        <span className="font-mono text-xs">{getValue<number>()}</span>
      ),
    },
  ];
}

export function ClaimsExplorer() {
  const router = useRouter();
  const { href } = useEmbed();
  const { data, error, loading } = useAsync(() => api.listClaims(), []);
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [filter, setFilter] = React.useState("");
  const columns = React.useMemo(() => buildColumns(href), [href]);

  const table = useReactTable({
    data: data ?? [],
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
        c.owner.toLowerCase().includes(needle)
      );
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const go = (id: string) => router.push(href(`/claims/${id}`));
  const rows = table.getRowModel().rows;

  return (
    <div>
      <PageHeader
        eyebrow="Claims"
        title="Claim explorer"
        description="Every claim the gate can cite. An answer only ships when a verified, in-date claim covers it."
      />
      <ClaimsSubnav />

      <div className="mb-3 max-w-sm">
        <label htmlFor="claims-filter" className="sr-only">
          Filter by statement or owner
        </label>
        <Input
          id="claims-filter"
          type="search"
          placeholder="Filter by statement or owner"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      {loading ? <LoadingState label="Loading claims" /> : null}
      {error ? <ErrorState error={error} /> : null}

      {data ? (
        rows.length === 0 ? (
          <EmptyState
            title="No claims match"
            body="Try a different word from the statement or the owner's name."
          />
        ) : (
          <div className="rounded-md border bg-card">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((hg) => (
                  <TableRow key={hg.id}>
                    {hg.headers.map((h) => {
                      const sorted = h.column.getIsSorted();
                      const Icon =
                        sorted === "asc"
                          ? ArrowUp
                          : sorted === "desc"
                            ? ArrowDown
                            : ArrowUpDown;
                      return (
                        <TableHead
                          key={h.id}
                          scope="col"
                          aria-sort={
                            sorted === "asc"
                              ? "ascending"
                              : sorted === "desc"
                                ? "descending"
                                : "none"
                          }
                        >
                          <button
                            type="button"
                            onClick={h.column.getToggleSortingHandler()}
                            className="inline-flex items-center gap-1 rounded-sm text-xs font-medium text-muted-foreground hover:text-foreground"
                          >
                            {flexRender(
                              h.column.columnDef.header,
                              h.getContext(),
                            )}
                            <Icon
                              className={cn(
                                "size-3",
                                sorted ? "opacity-100" : "opacity-40",
                              )}
                              aria-hidden
                            />
                          </button>
                        </TableHead>
                      );
                    })}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
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
                    className="cursor-pointer focus-visible:bg-muted/50 focus-visible:outline-none"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id} className="align-top">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )
      ) : null}
    </div>
  );
}
