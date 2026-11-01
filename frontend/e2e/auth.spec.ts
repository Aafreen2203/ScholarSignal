import { expect, test } from "@playwright/test";

const identity = () => `browser-${crypto.randomUUID()}@example.com`;
const password = "a sufficiently long passphrase";

test("registration persists a session, protects workspace, and logout clears it", async ({ page }) => {
  const email = identity();
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Browser Researcher");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create your account" }).click();

  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByText("Browser Researcher", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/workspace");
  await expect(page).toHaveURL(/\/login$/);
});

test("login through the Next proxy opens the protected workspace", async ({ page, request }) => {
  const email = identity();
  const created = await request.post("/api/v1/auth/register", {
    data: { email, password, display_name: "Login Researcher" },
  });
  expect(created.status()).toBe(201);

  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});

test("unauthenticated visits to workspace redirect to login", async ({ page }) => {
  await page.goto("/workspace");
  await expect(page).toHaveURL(/\/login$/);
});

test("Next proxy preserves the Redis rate-limit status and retry header", async ({ request }) => {
  const email = identity();
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const response = await request.post("/api/v1/auth/login", {
      data: { email, password: "incorrect password" },
    });
    expect(response.status()).toBe(401);
  }
  const limited = await request.post("/api/v1/auth/login", {
    data: { email, password: "incorrect password" },
  });
  expect(limited.status()).toBe(429);
  const retryAfter = Number(limited.headers()["retry-after"]);
  expect(retryAfter).toBeGreaterThan(0);
  expect(retryAfter).toBeLessThanOrEqual(900);
});

test("search page reaches FastAPI through the Next.js proxy", async ({ page }) => {
  await page.goto("/search");
  await expect(page.getByRole("heading", { name: /search the literature/i })).toBeVisible();
  await page.getByLabel("Research question or keywords").fill("climate adaptation");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/lexical · \d+ results/)).toBeVisible();
});
