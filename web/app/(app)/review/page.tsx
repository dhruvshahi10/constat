import { PageHeader } from "@/components/page-header";
import { ReviewQueue } from "@/components/screens/review-queue";

export default function ReviewPage() {
  return (
    <>
      <PageHeader
        eyebrow="Review"
        title="Review queue"
        description="Ranked by value, deal blockers and age. Approve, edit or route; nothing leaves without a human."
      />
      <ReviewQueue />
    </>
  );
}
