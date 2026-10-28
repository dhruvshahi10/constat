// Copy gate: no em dash (U+2014) or en dash (U+2013) anywhere under app/ or
// components/. The brand rule is mechanical so it never depends on a reviewer
// noticing. Exit 1 with file:line:col for every hit.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const targets = ["app", "components"].map((d) => join(root, d));
const exts = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".css", ".md", ".mdx", ".json"]);
const bad = /[–—]/g;

function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      if (name === "node_modules" || name === ".next") continue;
      walk(p, out);
    } else if (exts.has(name.slice(name.lastIndexOf(".")))) {
      out.push(p);
    }
  }
  return out;
}

const hits = [];
for (const t of targets) {
  let files = [];
  try {
    files = walk(t, []);
  } catch {
    continue;
  }
  for (const f of files) {
    const lines = readFileSync(f, "utf8").split("\n");
    lines.forEach((line, i) => {
      let m;
      bad.lastIndex = 0;
      while ((m = bad.exec(line)) !== null) {
        const which = m[0] === "—" ? "em dash" : "en dash";
        hits.push(`${relative(root, f)}:${i + 1}:${m.index + 1} ${which}`);
      }
    });
  }
}

if (hits.length) {
  console.error(`copy gate: ${hits.length} dash violation(s)`);
  for (const h of hits) console.error("  " + h);
  process.exit(1);
}
console.log("copy gate: clean");
