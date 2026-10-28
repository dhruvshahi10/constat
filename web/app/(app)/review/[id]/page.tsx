import { ReviewDetail } from "@/components/screens/review-detail";

export default async function ReviewItemPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  return <ReviewDetail id={id} initialEdit={sp.edit === "1"} />;
}
