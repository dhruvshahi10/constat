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
    command: `npm run build >/dev/null 2>&1 && npx next start -p ${PORT}`,
    url: `http://localhost:${PORT}/inbox`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
