"use client";

import { api } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { PageHeader, LoadingState, ErrorState } from "@/components/page-header";
import { DegradationNotice } from "@/components/shell/degradation-banner";
import { StatTile } from "@/components/stat-tile";

export function DegradationPage() {
  const { data, loading, error } = useAsync(() => api.degradation());
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!data) return null;
  const degraded = data.state === "degraded";
  return (
    <div>
      <PageHeader eyebrow="Operations" title={degraded ? "Running degraded" : "Running normally"} description="When the primary reviewer is idle for 72 hours the tenant degrades: approved and unchanged answers continue, everything novel or changed is held, the AE gets a dated status, deal blockers go to the named backup." />
      {degraded ? <DegradationNotice state={data} className="mb-6 py-2 text-sm" /> : null}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Reviewer" value={data.reviewer} hint={`idle ${data.reviewer_idle_hours} h`} tone={degraded ? "warn" : "default"} />
        <StatTile label="Named backup" value={data.backup ?? "none"} hint={data.backup ? "Receives deal blockers" : "Set one before the next absence"} tone={data.backup ? "default" : "critical"} />
        <StatTile label="Flowing" value={String(data.flowing)} hint="Approved and unchanged answers" tone="ok" />
        <StatTile label="Held" value={String(data.held)} hint="Novel or changed, waiting" tone="warn" />
      </div>
      <p className="mt-6 max-w-[70ch] text-sm text-muted-foreground">
        Nothing is lost while degraded. The queue is waiting, ranked, when the reviewer returns. Naming a backup is an admin action on the API (POST /degradation/backup) and is not exposed here yet.
      </p>
    </div>
  );
}
