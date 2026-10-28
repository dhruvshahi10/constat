import localFont from "next/font/local";
import { Funnel_Display, Inter } from "next/font/google";

// Constat theme: subset faces synced from constat/assets/fonts by
// scripts/sync-fonts.mjs.
export const newsreader = localFont({
  src: "./fonts/news.woff2",
  variable: "--font-newsreader",
  weight: "200 800",
  display: "swap",
});

export const archivo = localFont({
  src: "./fonts/arch.woff2",
  variable: "--font-archivo",
  weight: "100 900",
  display: "swap",
});

export const fragmentMono = localFont({
  src: "./fonts/mono.woff2",
  variable: "--font-fragment-mono",
  weight: "400",
  display: "swap",
});

// Native theme: Atlan's brand pair (atlan.com/brand/typography). Both are
// open-licence and self-hosted by next/font at build time.
export const funnelDisplay = Funnel_Display({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-funnel",
  display: "swap",
});

export const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const fontVariables = `${newsreader.variable} ${archivo.variable} ${fragmentMono.variable} ${funnelDisplay.variable} ${inter.variable}`;
