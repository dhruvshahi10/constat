"use client";

import { api } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { PageHeader, LoadingState, ErrorState, EmptyState } from "@/components/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export function Evals() {
  const { data, loading, error } = useAsync(() => api.evalRecords());
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  return (
    <div>
      <PageHeader eyebrow="Model evaluations" title="Every model change carries its record" description="No model id or prompt version changes without a new record. The judge scores phrasing only; the outcome is decided by the gates, never by a model." />
      {!data?.length ? (
        <EmptyState title="No evaluation record yet" />
      ) : (
        <div className="rounded-md border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead>Prompt</TableHead>
                <TableHead>Run</TableHead>
                <TableHead className="text-right">Dangerous</TableHead>
                <TableHead className="text-right">Weighted</TableHead>
                <TableHead className="text-right">Holdout</TableHead>
                <TableHead>Judge</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.model_id}</TableCell>
                  <TableCell className="font-mono text-xs">{r.prompt_version}</TableCell>
                  <TableCell className="text-muted-foreground">{r.run_at}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", r.dangerous_failures > 0 ? "text-status-critical" : "text-status-ok")}>{r.dangerous_failures}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", r.weighted_score < 0.95 && "text-status-warn")}>{r.weighted_score.toFixed(2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.holdout_score.toFixed(2)}</TableCell>
                  <TableCell className="text-muted-foreground">{r.judge ?? "none"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
