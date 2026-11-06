import { notFound } from "next/navigation";
import { EmbedFrame } from "@/components/embed-frame";
import { Inbox } from "@/components/screens/inbox";
import { QuestionnaireItems } from "@/components/screens/questionnaire-items";
import { ReviewQueue } from "@/components/screens/review-queue";
import { ReviewDetail } from "@/components/screens/review-detail";
import { ClaimsExplorer } from "@/components/screens/claims-explorer";
import { ClaimDetail } from "@/components/screens/claim-detail";
import { Proposals } from "@/components/screens/proposals";
import { Freshness } from "@/components/screens/freshness";
import { ClaimImport } from "@/components/screens/claim-import";
import { ClaimAuthor } from "@/components/screens/claim-author";
import { Metrics } from "@/components/screens/metrics";
import { ProvenanceChain } from "@/components/screens/provenance-chain";
import { ProvenanceList } from "@/components/screens/provenance-list";
import { TrustPreview } from "@/components/screens/trust-preview";
import { Evals } from "@/components/screens/evals";

/**
 * /embed/<view>[/<id>] renders the same screens as the app without chrome,
 * for the iframe inside Atlan. The view name is also what the handshake
 * echoes back in constat:ack.
 */
export default async function EmbedPage({
  params,
  searchParams,
}: {
  params: Promise<{ view: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { view } = await params;
  const sp = await searchParams;
  const [head, id, tail] = view;
  const viewName = view.join("/");

  let screen: React.ReactNode;
  switch (head) {
    case "inbox":
      screen = id ? <QuestionnaireItems id={id} /> : <Inbox />;
      break;
    case "review":
      screen = id ? <ReviewDetail id={id} initialEdit={sp.edit === "1"} /> : <ReviewQueue />;
      break;
    case "claims":
      if (id === "proposals") screen = <Proposals />;
      else if (id === "freshness") screen = <Freshness />;
      else if (id === "import") screen = <ClaimImport />;
      else if (id === "author") screen = <ClaimAuthor />;
      else if (id) screen = <ClaimDetail id={id} />;
      else screen = <ClaimsExplorer />;
      break;
    case "provenance":
      screen = <ProvenanceList />;
      break;
    case "questions":
      if (id && tail === "provenance") screen = <ProvenanceChain id={id} />;
      else notFound();
      break;
    case "metrics":
      screen = <Metrics />;
      break;
    case "trust":
      screen = <TrustPreview />;
      break;
    case "evals":
      screen = <Evals />;
      break;
    default:
      notFound();
  }

  return <EmbedFrame view={viewName}>{screen}</EmbedFrame>;
}
