// Copies the three subset woff2 faces from the Python package (the source of
// truth, constat/brand.py) into web/app/fonts so next/font/local can inline
// them. Run after the Python package changes a face. Idempotent.
import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "constat", "assets", "fonts");
const dst = join(here, "..", "app", "fonts");
mkdirSync(dst, { recursive: true });
let copied = 0;
for (const f of ["news.woff2", "arch.woff2", "mono.woff2"]) {
  const from = join(src, f);
  if (!existsSync(from)) {
    console.error(`missing ${from}`);
    process.exit(1);
  }
  copyFileSync(from, join(dst, f));
  copied += 1;
}
console.log(`synced ${copied} faces into app/fonts`);
