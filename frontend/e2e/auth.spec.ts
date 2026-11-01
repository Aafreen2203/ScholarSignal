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
  await page.getByLabel("Retrieval method").selectOption("lexical");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/PostgreSQL English full-text ranking/)).toBeVisible();
});

test("authenticated workspace persists saved papers, collections, and notes through the proxy", async ({ page, request }) => {
  const email = identity();
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Workspace Researcher");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create your account" }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  const libraryResponse = await request.get("/api/v1/search", { params: { q: "protein structure", method: "lexical" } });
  const records = (await libraryResponse.json()).results;
  if (records.length > 0) {
    await page.goto("/search");
    await page.getByLabel("Research question or keywords").fill("protein structure");
    await page.getByLabel("Retrieval method").selectOption("lexical");
    await page.getByRole("button", { name: "Search" }).click();
    await page.getByRole("button", { name: "Save paper" }).first().click();
    await expect(page.getByRole("status").getByText("Saved to your research desk.")).toBeVisible();
    await page.goto("/workspace");
    await expect(page.getByRole("link", { name: records[0].title })).toBeVisible();
  }
  await page.getByLabel("Name", { exact: true }).fill("Reading list");
  await page.getByRole("button", { name: "Create collection" }).click();
  const collectionEntry = page.locator(".desk-compact-list strong").filter({ hasText: "Reading list" });
  await expect(collectionEntry).toBeVisible();
  if (records.length > 0) {
    await page.getByLabel(/Add .* to collection/).selectOption({ label: "Reading list" });
    await expect(page.getByText("1 paper", { exact: true })).toBeVisible();
    await expect(page.locator(".collection-paper-list").getByRole("link", { name: records[0].title })).toBeVisible();
    await page.locator(".collection-paper-list").getByRole("button", { name: "Remove" }).click();
    await expect(page.getByText("No papers in this collection yet.")).toBeVisible();
  }
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(collectionEntry).toHaveCount(0);
  await page.getByLabel("Title", { exact: true }).fill("Research question");
  await page.getByLabel("Note", { exact: true }).fill("Compare the limitations across these studies.");
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.getByText("Compare the limitations across these studies.")).toBeVisible();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Compare the limitations across these studies.")).toHaveCount(0);
});

test("paper detail and related results use persisted publication records", async ({ page, request }) => {
  const response = await request.get("/api/v1/search", { params: { q: "protein structure", method: "lexical" } });
  expect(response.status()).toBe(200);
  const results = (await response.json()).results;
  test.skip(results.length === 0, "This clean test environment has no ingested publication corpus.");
  const paper = results[0];
  await page.goto(`/papers/${paper.id}`);
  await expect(page.getByRole("heading", { name: paper.title })).toBeVisible();
  await expect(page.getByText(paper.openalex_id)).toBeVisible();
  const related = await request.get(`/api/v1/publications/${paper.id}/related`);
  expect(related.status()).toBe(200);
  expect((await related.json()).retrieval_method).toBe("semantic_similarity");
});
