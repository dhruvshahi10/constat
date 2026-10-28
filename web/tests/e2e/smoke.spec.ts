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

test("the command palette answers or refuses", async ({ page }) => {
  await page.goto("/inbox");
  await page.keyboard.press("ControlOrMeta+k");
  const input = page.getByPlaceholder(/ask a question/i);
  await expect(input).toBeVisible();
  await input.fill("Is customer data encrypted at rest?");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("verdict-card")).toContainText(/answer/i);
});

test("embedded view carries no chrome and the dev shell completes the handshake", async ({ page }) => {
  await page.goto("/embed/review");
  await expect(page.locator("nav[aria-label='Primary']")).toHaveCount(0);
  await expect(page.locator("table")).toBeVisible();

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

test("CSP frame-ancestors differs between /embed and the rest", async ({ request }) => {
  const embed = await request.get("/embed/review");
  expect(embed.headers()["content-security-policy"]).toMatch(/frame-ancestors 'self' https:\/\/\*\.atlan\.com/);
  expect(embed.headers()["x-frame-options"]).toBeUndefined();
  const app = await request.get("/review");
  expect(app.headers()["content-security-policy"]).toMatch(/frame-ancestors 'none'/);
});
