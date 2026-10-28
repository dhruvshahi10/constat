"use client";

import * as React from "react";
import Link from "next/link";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Nav } from "@/components/shell/nav";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { DegradationBanner } from "@/components/shell/degradation-banner";
import { CommandPalette } from "@/components/shell/command-palette";
import { AskBar } from "@/components/shell/ask-bar";

function Wordmark({ onSidebar }: { onSidebar?: boolean }) {
  return (
    <Link href="/inbox" className="flex items-center gap-2" aria-label="Constat home">
      <span aria-hidden className={onSidebar ? "size-2 bg-sidebar-primary" : "size-2 bg-primary"} />
      <span className={onSidebar ? "font-heading text-lg leading-none font-semibold tracking-tight text-sidebar-accent-foreground" : "font-heading text-lg leading-none font-semibold tracking-tight"}>
        Constat
      </span>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = React.useState(false);
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-52 shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-2.5 py-4 text-sidebar-foreground md:flex">
        <div className="px-2.5 pb-5">
          <Wordmark onSidebar />
        </div>
        <Nav />
        <p className="mt-auto px-2.5 font-mono text-[10px] leading-relaxed opacity-70">
          Every answer rests on a claim, or it is refused.
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
          <div className="flex h-12 items-center gap-2 px-3 sm:px-4">
            <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
              <SheetTrigger render={<Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open navigation" />}>
                <Menu aria-hidden />
              </SheetTrigger>
              <SheetContent side="left" className="w-64 bg-sidebar p-4 text-sidebar-foreground">
                <SheetHeader className="p-0">
                  <SheetTitle className="font-heading text-lg font-semibold text-sidebar-accent-foreground">Constat</SheetTitle>
                </SheetHeader>
                <Nav onNavigate={() => setMenuOpen(false)} />
              </SheetContent>
            </Sheet>
            <span className="md:hidden">
              <Wordmark />
            </span>
            <AskBar className="hidden sm:block" />
            <CommandPalette />
            <ThemeToggle />
          </div>
          <div className="px-3 pb-2 sm:hidden">
            <AskBar />
          </div>
          <DegradationBanner className="mx-3 mb-2 sm:mx-4" />
        </header>
        <main className="flex-1 px-4 py-5 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
