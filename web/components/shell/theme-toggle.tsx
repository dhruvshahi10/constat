"use client";

import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/components/theme-provider";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const next = theme === "constat" ? "native" : "constat";
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggleTheme}
      aria-label={`Switch to the ${next} theme`}
      title={`Theme: ${theme}. Switch to ${next}.`}
      data-testid="theme-toggle"
    >
      {theme === "constat" ? <Sun aria-hidden /> : <Moon aria-hidden />}
    </Button>
  );
}
