import { notFound } from "next/navigation";
import { DEV_SHELL_ENABLED } from "@/lib/dev-shell";
import { AtlanShell } from "@/components/dev/atlan-shell";

export const metadata = { title: "Atlan shell simulator" };

export default function AtlanShellPage() {
  if (!DEV_SHELL_ENABLED) notFound();
  return <AtlanShell />;
}
