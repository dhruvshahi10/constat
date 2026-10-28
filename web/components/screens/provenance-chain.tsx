"use client";

import * as React from "react";
import Link from "next/link";
import { ReactFlow, Background, type Node, type Edge, type NodeProps, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, type Claim, type QuestionDetail } from "@/lib/api";
import { useAsync } from "@/lib/use-api";
import { useEmbed } from "@/lib/embed";
import { PageHeader, LoadingState, ErrorState } from "@/components/page-header";
import { OutcomeBadge, DifficultyBadge } from "@/components/badges";
import { cn } from "@/lib/utils";

type ChainData = { kind: "question" | "claim" | "evidence" | "test"; title: string; body: string; href?: string };
type ChainNode = Node<ChainData, "chain">;

function ChainNodeView({ data }: NodeProps<ChainNode>) {
  const tone = {
    question: "border-l-primary",
    claim: "border-l-status-ok",
    evidence: "border-l-status-info",
    test: "border-l-status-warn",
  }[data.kind];
  return (
    <div className={cn("w-64 rounded-md border border-l-2 bg-card p-3 text-left text-card-foreground shadow-sm", tone)}>
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <p className="eyebrow mb-1">{data.kind}</p>
      <p className="text-sm font-medium leading-snug">{data.title}</p>
      <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{data.body}</p>
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  );
}

const nodeTypes = { chain: ChainNodeView };

function buildGraph(detail: QuestionDetail, claims: Claim[]): { nodes: ChainNode[]; edges: Edge[] } {
  const nodes: ChainNode[] = [
    {
      id: "q",
      type: "chain",
      position: { x: 0, y: 0 },
      data: { kind: "question", title: `${detail.item.customer} question ${detail.item.ordinal}`, body: detail.item.text },
    },
  ];
  const edges: Edge[] = [];
  claims.forEach((c, ci) => {
    const cid = `c${ci}`;
    nodes.push({ id: cid, type: "chain", position: { x: 320, y: ci * 160 }, data: { kind: "claim", title: `${c.owner} owns this claim`, body: c.statement } });
    edges.push({ id: `q-${cid}`, source: "q", target: cid, animated: false });
    c.evidence.forEach((e, ei) => {
      const eid = `${cid}e${ei}`;
      const isTest = e.kind === "vanta_test";
      nodes.push({
        id: eid,
        type: "chain",
        position: { x: isTest ? 960 : 640, y: ci * 160 + ei * 120 },
        data: { kind: isTest ? "test" : "evidence", title: e.ref, body: `${e.kind}${e.checked_on ? `, checked ${e.checked_on}` : ""}` },
      });
      edges.push({ id: `${cid}-${eid}`, source: cid, target: eid });
    });
  });
  return { nodes, edges };
}

export function ProvenanceChain({ id }: { id: string }) {
  const { href } = useEmbed();
  const { data, loading, error } = useAsync(() => api.getQuestion(id), [id]);
  const graph = React.useMemo(() => (data ? buildGraph(data, data.claims) : null), [data]);
  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!data || !graph) return null;

  return (
    <div>
      <Link href={href("/provenance")} className="eyebrow mb-3 inline-block hover:text-foreground">
        Back to provenance
      </Link>
      <PageHeader
        eyebrow={`${data.item.customer} question ${data.item.ordinal}`}
        title={data.item.text}
        actions={
          <>
            <OutcomeBadge outcome={data.verdict.outcome} />
            <DifficultyBadge difficulty={data.verdict.difficulty} />
          </>
        }
      />
      <div className="h-[420px] overflow-hidden rounded-md border bg-muted/40" data-testid="provenance-graph">
        <ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} fitView proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false} zoomOnScroll={false} panOnScroll>
          <Background gap={16} />
        </ReactFlow>
      </div>

      {/* The text chain: readable by a screen reader and in a printout. */}
      <ol className="mt-6 space-y-2 font-mono text-xs" aria-label="Provenance chain as text">
        <li>
          <span className="eyebrow">question</span> {data.item.text}
        </li>
        {data.claims.length === 0 ? (
          <li className="text-status-critical">No claim supports this answer. That is why the gate refused it.</li>
        ) : null}
        {data.claims.map((c) => (
          <li key={c.id} className="ml-4">
            <span className="eyebrow">claim</span>{" "}
            <Link href={href(`/claims/${c.id}`)} className="text-primary underline-offset-2 hover:underline">
              {c.id}
            </Link>{" "}
            @ {c.version_hash}, owner {c.owner}, valid until {c.valid_until}
            <ul className="ml-4">
              {c.evidence.map((e) => (
                <li key={e.ref}>
                  <span className="eyebrow">{e.kind === "vanta_test" ? "test" : "evidence"}</span> {e.ref}
                  {e.checked_on ? `, checked ${e.checked_on}` : ""}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
