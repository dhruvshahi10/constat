import { ClaimDetail } from "@/components/screens/claim-detail";

export default async function ClaimPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClaimDetail id={id} />;
}
