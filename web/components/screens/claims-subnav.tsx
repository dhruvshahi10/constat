"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useEmbed } from "@/lib/embed";

const TABS = [
  { path: "/claims", label: "Explorer" },
  { path: "/claims/proposals", label: "Proposals" },
  { path: "/claims/freshness", label: "Freshness" },
] as const;

function isActive(bare: string, path: string): boolean {
  if (path === "/claims") {
    // Explorer owns /claims and /claims/[id], but not the sibling sections.
    return bare === "/claims" || (bare.startsWith("/claims/") && !TABS.slice(1).some((t) => bare.startsWith(t.path)));
  }
  return bare === path || bare.startsWith(path + "/");
}

/** Section switcher shared by the three claims screens, bare or embedded. */
export function ClaimsSubnav({ className }: { className?: string }) {
  const pathname = usePathname() ?? "/claims";
  const { href } = useEmbed();
  const bare = pathname.replace(/^\/embed(?=\/|$)/, "") || "/";
  return (
    <nav aria-label="Claims sections" className={cn("mb-6 flex flex-wrap gap-1 border-b", className)}>
      {TABS.map((tab) => {
        const active = isActive(bare, tab.path);
        return (
          <Link
            key={tab.path}
            href={href(tab.path)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm transition-colors",
              active
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
