import { test, expect, type Page } from "@playwright/test";

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "phone", width: 390, height: 844 },
];

const IGNORED = [/favicon/i, /hydrat/i];

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && !IGNORED.some((re) => re.test(msg.text()))) errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

for (const vp of VIEWPORTS) {
  test.describe(`${vp.name} ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("/review loads with zero console errors", async ({ page }) => {
      const errors = collectErrors(page);
      await page.goto("/review");
      await expect(page.getByRole("heading", { name: /review queue/i })).toBeVisible();
      await expect(page.locator("table")).toBeVisible();
      await expect(page.locator("tbody tr").first()).toBeVisible();
      expect(errors).toEqual([]);
    });

    test("/review/[id] renders the refusal moment with zero console errors", async ({ page }) => {
      const errors = collectErrors(page);
      await page.goto("/review/q_01J9A007");
      await expect(page.getByTestId("draft-pane")).toBeVisible();
      await expect(page.getByTestId("gate-stamp")).toBeVisible();
      await expect(page.getByTestId("gate-stamp")).toContainText(/refused/i);
      await expect(page.locator(".draft-struck")).toBeVisible();
      expect(errors).toEqual([]);
    });

    test("an answerable item shows no stamp", async ({ page }) => {
      await page.goto("/review/q_01J9A002");
      await expect(page.getByTestId("draft-pane")).toBeVisible();
      await expect(page.getByTestId("gate-stamp")).toHaveCount(0);
    });
  });
}

test("both themes pass the ?theme= switch and the toggle", async ({ page }) => {
  await page.goto("/review?theme=native");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "native");
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "constat");
  await page.goto("/inbox");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "constat");
});

test("the Ask bar answers or refuses in place", async ({ page }) => {
  await page.goto("/inbox");
  const ask = page.getByTestId("ask-input").first();
  await ask.fill("Is customer data encrypted at rest?");
  await ask.press("Enter");
  await expect(page.getByTestId("verdict-card")).toHaveAttribute("data-outcome", "ANSWER");
  await page.keyboard.press("Escape");
  await ask.fill("Do you guarantee 99.99% uptime with service credits?");
  await ask.press("Enter");
  await expect(page.getByTestId("verdict-card")).toHaveAttribute("data-outcome", "HOLD_HUMAN");
});

test("the command palette opens and jumps", async ({ page }) => {
  await page.goto("/inbox");
  await page.getByTestId("open-palette").click();
  const input = page.getByPlaceholder(/ask a question, or jump/i);
  await expect(input).toBeVisible();
  await input.fill("claims");
  await page.getByRole("option", { name: /^claims$/i }).click();
  await expect(page).toHaveURL(/\/claims$/);
});

test("the review workbench keeps the selected item in the URL", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/review?item=q_01J9A007");
  await expect(page.getByTestId("gate-stamp")).toBeVisible();
  await expect(page.getByTestId("provenance-rail")).toBeVisible();
});

test("claim import previews, locks risky rows, and commits as proposals", async ({ page }) => {
  await page.goto("/claims/import");
  await page.locator("input[type=file]").setInputFiles({ name: "orbit-answers.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("x") });
  const customer = page.getByLabel(/customer/i).first();
  if (await customer.isVisible()) await customer.fill("Orbit Finance");
  await page.getByRole("button", { name: /preview|import|upload/i }).last().click();
  const commit = page.getByRole("button", { name: /open \d+ proposal/i });
  await expect(commit).toBeVisible({ timeout: 10_000 });
  await commit.click();
  await expect(page.getByRole("link", { name: /review proposals/i })).toBeVisible();
});

const TENANT = process.env.E2E_TENANT_ORIGIN ?? "https://tenant.atlan.com";

test("embedded view carries no chrome", async ({ page }) => {
  await page.goto("/embed/review");
  await expect(page.locator("nav[aria-label='Primary']")).toHaveCount(0);
  await expect(page.locator("table")).toBeVisible();
});

test("dev shell: handshake in development, absent in production", async ({ page, request }) => {
  const probe = await request.get("/dev/atlan-shell");
  if (probe.status() === 404) {
    // Production build: the simulator must not ship.
    expect(probe.status()).toBe(404);
    return;
  }
  await page.goto("/dev/atlan-shell");
  const log = page.getByTestId("shell-log");
  await expect(log).toContainText("constat:ready", { timeout: 20_000 });
  await expect(log).toContainText("atlan:init");
  await expect(log).toContainText("constat:ack");
  const frame = page.frameLocator("[data-testid='shell-frame']");
  await expect(frame.locator("html")).toHaveAttribute("data-theme", "native");
  await expect(frame.locator("[data-embedded='true']")).toHaveAttribute("data-host-user", "fde@atlan.com");
  await page.getByTestId("shell-theme").click();
  await expect(frame.locator("html")).toHaveAttribute("data-theme", "constat");
});

test("CSP: /embed allows only the configured frame ancestors, the rest denies", async ({ request }) => {
  const embed = await request.get("/embed/review");
  const csp = embed.headers()["content-security-policy"] ?? "";
  expect(embed.headers()["x-frame-options"]).toBeUndefined();
  if (process.env.E2E_MODE === "dev") {
    expect(csp).toMatch(/frame-ancestors 'self' https:\/\/\*\.atlan\.com/);
  } else {
    expect(csp).toBe(`frame-ancestors ${TENANT}`);
  }
  const app = await request.get("/review");
  expect(app.headers()["content-security-policy"]).toMatch(/frame-ancestors 'none'/);
  expect(app.headers()["x-frame-options"]).toBe("DENY");
});
