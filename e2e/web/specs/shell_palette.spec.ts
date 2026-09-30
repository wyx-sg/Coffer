// e2e/web/specs/shell_palette.spec.ts
//
// The ⌘K command palette in a real browser (spec web-ui "Jump to any page or
// object from a command palette"): it jumps to a page, to an object found by
// its name, and to a Settings tab over the current page. Plain tests; the
// component tests (CommandPalette.test.tsx) carry the scenarios' markers.

import { expect, test, type Page } from "@playwright/test";
import {
  beforeEachInjectToken,
  deregisterMcpServer,
  generateUniqueName,
  readDaemonToken,
} from "./_helpers";

beforeEachInjectToken();

const MOD = process.platform === "darwin" ? "Meta" : "Control";

async function openPalette(page: Page) {
  await page.keyboard.press(`${MOD}+k`);
  const input = page.getByRole("combobox", {
    name: /search pages/i,
  });
  await expect(input).toBeFocused();
  return input;
}

test("the palette jumps to a page", async ({ page }) => {
  await page.goto("/agents");
  await expect(
    page.getByRole("heading", { level: 1, name: "Agents" }),
  ).toBeVisible();
  const input = await openPalette(page);
  await input.fill("act");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/activity$/);
  await expect(input).toHaveCount(0);
});

test("the palette jumps to an object by its name", async ({ page }) => {
  const name = generateUniqueName("e2epalette");
  const { token, port } = readDaemonToken();
  const r = await fetch(`http://127.0.0.1:${port}/api/v1/resources`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    body: JSON.stringify({
      kind: "mcp_server",
      name,
      config: { transport: { type: "stdio", command: "true", args: [] } },
    }),
  });
  expect(r.ok).toBe(true);
  try {
    await page.goto("/activity");
    const input = await openPalette(page);
    await input.fill(name);
    await expect(
      page.getByRole("option", { name: new RegExp(name) }),
    ).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`/mcp-servers/${name}$`));
  } finally {
    await deregisterMcpServer(name);
  }
});

test("the palette opens a Settings tab over the current page", async ({
  page,
}) => {
  await page.goto("/skills");
  await expect(
    page.getByRole("heading", { level: 1, name: "Skills" }),
  ).toBeVisible();
  const input = await openPalette(page);
  await input.fill("data");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/settings\/data$/);
  await expect(page.getByTestId("settings-modal")).toBeVisible();
  // The Skills page stays underneath.
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/\/skills$/);
});
