import { expect, test } from "@playwright/test";

test.describe("Coffer scaffolding — end-to-end", () => {
  test("frontend renders the Coffer landing page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Coffer")).toBeVisible();
    await expect(page.getByText(/Local-first AI agent vault/i)).toBeVisible();
  });

  test("backend /health endpoint returns ok with version", async ({ request }) => {
    const response = await request.get("http://localhost:8000/health");
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body).toMatchObject({ status: "ok", version: "0.1.0" });
  });

  test("backend /openapi.json exposes the HealthResponse schema", async ({ request }) => {
    const response = await request.get("http://localhost:8000/openapi.json");
    expect(response.ok()).toBeTruthy();
    const schema = await response.json();
    expect(schema.openapi).toMatch(/^3\./);
    expect(schema.paths["/health"]).toBeDefined();
    expect(schema.components.schemas.HealthResponse).toBeDefined();
  });
});
