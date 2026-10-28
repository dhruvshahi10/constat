"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Inbox,
  ListChecks,
  ShieldCheck,
  GitBranch,
  BarChart3,
  Globe,
  FlaskConical,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Any pathname starting with one of these counts as active. */
  match?: string[];
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/review", label: "Review", icon: ListChecks },
  { href: "/claims", label: "Claims", icon: ShieldCheck, match: ["/claims"] },
  { href: "/provenance", label: "Provenance", icon: GitBranch, match: ["/provenance", "/questions"] },
  { href: "/metrics", label: "Metrics", icon: BarChart3, match: ["/metrics", "/ops"] },
  { href: "/trust/preview", label: "Trust", icon: Globe, match: ["/trust"] },
  { href: "/evals", label: "Evals", icon: FlaskConical },
];

export function isActive(pathname: string, item: NavItem): boolean {
  const prefixes = item.match ?? [item.href];
  return prefixes.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

export function Nav({ onNavigate, className }: { onNavigate?: () => void; className?: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className={cn("flex flex-col gap-0.5", className)}>
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
