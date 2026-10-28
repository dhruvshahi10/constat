"use client";

import Link from "next/link";
import { api, type QuestionItem } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { PageHeader, LoadingState, ErrorState, EmptyState } from "@/components/page-header";
import { StateBadge, DifficultyBadge } from "@/components/badges";

export function ProvenanceList() {
  const { href } = useEmbed();
  const { data, loading, error } = useAsync(async () => {
    const qs = await api.listQuestionnaires();
    const lists = await Promise.all(qs.map((q) => api.listItems(q.id)));
    return lists.flat().filter((i): i is QuestionItem => !!i.claim_id || !!i.final_answer);
  });
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  return (
    <div>
      <PageHeader eyebrow="Provenance" title="Where every answer comes from" description="Question to claim to evidence to the test that checks it. The default way to look at an answer." />
      {!data?.length ? (
        <EmptyState title="No answer rests on a claim yet" />
      ) : (
        <ul className="divide-y rounded-md border bg-card">
          {data.map((i) => (
            <li key={i.id}>
              <Link href={href(`/questions/${i.id}/provenance`)} className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-muted/60">
                <span className="font-mono text-[11px] text-muted-foreground">{i.customer}</span>
                <span className="min-w-0 flex-1 truncate text-sm">{i.text}</span>
                <DifficultyBadge difficulty={i.difficulty} />
                <StateBadge state={i.state} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
