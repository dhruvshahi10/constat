import localFont from "next/font/local";

// Subset faces synced from constat/assets/fonts by scripts/sync-fonts.mjs.
// They are the Constat theme's type; the native theme uses the system stack.
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

export const fontVariables = `${newsreader.variable} ${archivo.variable} ${fragmentMono.variable}`;
