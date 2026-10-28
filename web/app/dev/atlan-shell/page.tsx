import { notFound } from "next/navigation";
import { DEV_SHELL_ENABLED } from "@/lib/dev-shell";
import { AtlanShell } from "@/components/dev/atlan-shell";

export const metadata = { title: "Atlan shell simulator" };
// Rendered per request so a production build answers a real 404, not a
// prerendered not-found page with status 200.
export const dynamic = "force-dynamic";

export default function AtlanShellPage() {
  if (!DEV_SHELL_ENABLED) notFound();
  return <AtlanShell />;
}
