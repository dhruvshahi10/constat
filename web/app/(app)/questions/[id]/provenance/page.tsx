import { ProvenanceChain } from "@/components/screens/provenance-chain";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProvenanceChain id={id} />;
}
