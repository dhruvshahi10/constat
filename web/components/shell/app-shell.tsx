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

function Wordmark() {
  return (
    <Link href="/inbox" className="flex items-center gap-2" aria-label="Constat home">
      <span aria-hidden className="size-2 bg-primary" />
      <span className="font-heading text-lg leading-none tracking-tight">Constat</span>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = React.useState(false);
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-56 shrink-0 flex-col border-r bg-sidebar px-3 py-4 md:flex">
        <div className="px-2.5 pb-5">
          <Wordmark />
        </div>
        <Nav />
        <p className="mt-auto px-2.5 font-mono text-[10px] leading-relaxed text-muted-foreground">
          Every answer rests on a claim, or it is refused.
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur sm:px-4">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger render={<Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open navigation" />}>
              <Menu aria-hidden />
            </SheetTrigger>
            <SheetContent side="left" className="w-64 bg-sidebar p-4">
              <SheetHeader className="p-0">
                <SheetTitle className="font-heading text-lg font-normal">Constat</SheetTitle>
              </SheetHeader>
              <Nav onNavigate={() => setMenuOpen(false)} />
            </SheetContent>
          </Sheet>
          <span className="md:hidden">
            <Wordmark />
          </span>
          <div className="min-w-0 flex-1">
            <DegradationBanner compact className="max-w-full" />
          </div>
          <CommandPalette />
          <ThemeToggle />
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
