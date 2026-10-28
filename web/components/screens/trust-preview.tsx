"use client";

import { api } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { PageHeader, LoadingState, ErrorState, EmptyState } from "@/components/page-header";

export function TrustPreview() {
  const { data, loading, error } = useAsync(() => api.trustPreview());
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  return (
    <div>
      <PageHeader eyebrow="Trust preview" title="What the public page would say" description="Only verified claims with a public audience. Publishing to the trust centre stays a manual, human step; this page never publishes." />
      {!data?.length ? (
        <EmptyState title="No public claim is verified" />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.map((e) => (
            <li key={e.claim_id} className="rounded-md border bg-card p-4">
              <p className="font-heading text-lg leading-snug">{e.statement}</p>
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                verified {e.last_verified}
                {e.evidence.length ? `, evidence: ${e.evidence.join(", ")}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
