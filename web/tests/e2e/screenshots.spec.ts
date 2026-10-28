import { test } from "@playwright/test";
import { mkdirSync } from "node:fs";

const SCREENS: Array<[string, string]> = [
  ["inbox", "/inbox"],
  ["inbox-questionnaire", "/inbox/qn_01J9ACME"],
  ["review", "/review"],
  ["review-refused", "/review/q_01J9A007"],
  ["review-held", "/review/q_01J9A003"],
  ["review-answer", "/review/q_01J9A002"],
  ["claims", "/claims"],
  ["claim-detail", "/claims/clm_01J9ENCRYPT"],
  ["claims-proposals", "/claims/proposals"],
  ["claims-freshness", "/claims/freshness"],
  ["provenance", "/questions/q_01J9A001/provenance"],
  ["metrics", "/metrics"],
  ["trust-preview", "/trust/preview"],
  ["evals", "/evals"],
  ["ops-degradation", "/ops/degradation"],
  ["embed-review", "/embed/review"],
  ["dev-atlan-shell", "/dev/atlan-shell"],
];

mkdirSync("screenshots", { recursive: true });

for (const theme of ["constat", "native"] as const) {
  for (const [name, path] of SCREENS) {
    for (const [vpName, width] of [
      ["1440", 1440],
      ["390", 390],
    ] as const) {
      test(`${theme} ${name} ${vpName}`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
        await page.emulateMedia({ reducedMotion: "reduce" });
        const join = path.includes("?") ? "&" : "?";
        await page.goto(`${path}${join}theme=${theme}`);
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(300);
        await page.screenshot({ path: `screenshots/${theme}/${name}-${vpName}.png`, fullPage: true });
      });
    }
  }
}
