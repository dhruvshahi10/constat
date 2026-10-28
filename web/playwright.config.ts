import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.PORT ?? 3100);

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  retries: 0,
  workers: 2,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
  },
  webServer: {
    // Built the way a tenant deployment is: one allowed frame ancestor.
    command: `NEXT_PUBLIC_ATLAN_ORIGINS=${process.env.E2E_TENANT_ORIGIN ?? "https://tenant.atlan.com"} npm run build >/dev/null 2>&1 && npx next start -p ${PORT}`,
    url: `http://localhost:${PORT}/inbox`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
