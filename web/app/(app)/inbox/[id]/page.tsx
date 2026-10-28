import { QuestionnaireItems } from "@/components/screens/questionnaire-items";

export default async function QuestionnairePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <QuestionnaireItems id={id} />;
}
