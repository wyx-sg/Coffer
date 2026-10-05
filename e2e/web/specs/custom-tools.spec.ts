// e2e/web/specs/custom-tools.spec.ts
//
// The Custom tools page in a real browser against the isolated daemon (change
// revise-web-ui-ia, spec web-ui "Manage custom tool groups on their own page"): an
// OpenAPI file imported into a new group, the group page with its tools, the
// tool drawer's Test calling a real upstream (a tiny HTTP server this spec
// starts on 127.0.0.1), and a group created over REST staying off the MCP
// servers page. Plain tests until the change is archived (its task 7.14d).

import { expect, test } from "@playwright/test";
import * as http from "node:http";
import type { AddressInfo } from "node:net";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

let upstream: http.Server;
let upstreamUrl = "";

test.beforeAll(async () => {
  upstream = http.createServer((req, res) => {
    const match = /^\/items\/([^/?]+)/.exec(req.url ?? "");
    res.setHeader("Content-Type", "application/json");
    if (req.method === "GET" && match) {
      res.end(JSON.stringify({ id: decodeURIComponent(match[1]), ok: true }));
      return;
    }
    res.statusCode = 404;
    res.end(JSON.stringify({ error: "not found" }));
  });
  await new Promise<void>((resolve) => upstream.listen(0, "127.0.0.1", resolve));
  upstreamUrl = `http://127.0.0.1:${(upstream.address() as AddressInfo).port}`;
});

test.afterAll(async () => {
  await new Promise<void>((resolve) => upstream.close(() => resolve()));
});

/** A throwaway group name: lowercase, digits, up to 24 characters. */
function groupName(prefix: string): string {
  return `${prefix}${Date.now().toString(36)}`;
}

async function api(method: string, route: string, body?: unknown): Promise<Response> {
  const { token, port } = readDaemonToken();
  return fetch(`http://127.0.0.1:${port}/api/v1${route}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function deleteGroup(name: string): Promise<void> {
  await api("DELETE", `/custom-tools/${encodeURIComponent(name)}`).catch(() => undefined);
}

function spec(): string {
  return JSON.stringify({
    openapi: "3.0.3",
    info: { title: "Items API", version: "1.0.0" },
    servers: [{ url: upstreamUrl }],
    paths: {
      "/items/{id}": {
        get: {
          operationId: "getItem",
          summary: "Read one item",
          parameters: [{ name: "id", in: "path", required: true, schema: { type: "string" } }],
          responses: { "200": { description: "The item" } },
        },
      },
      "/items": {
        post: {
          operationId: "createItem",
          summary: "Create an item",
          requestBody: {
            content: {
              "application/json": {
                schema: { type: "object", properties: { name: { type: "string" } } },
              },
            },
          },
          responses: { "201": { description: "Created" } },
        },
      },
    },
  });
}

test("an OpenAPI file becomes a group, and a tool's Test calls the API from the drawer", async ({
  page,
}) => {
  const name = groupName("cte2e");
  try {
    await page.goto("/custom-tools");
    await page.getByRole("button", { name: "Add custom tool" }).first().click();
    const choose = page.getByRole("dialog");
    // The group comes first; its select starts on New group, which offers the two ways to start it.
    await choose.getByRole("radio", { name: /Import an OpenAPI spec/ }).click();
    await choose.getByRole("button", { name: "Continue" }).click();

    const importDialog = page.getByRole("dialog", { name: "Import an OpenAPI spec" });
    await importDialog.getByLabel("Group name").fill(name);
    await importDialog.getByRole("radio", { name: "File" }).click();
    await importDialog.locator('input[type="file"]').setInputFiles({
      name: "items.json",
      mimeType: "application/json",
      buffer: Buffer.from(spec()),
    });
    await expect(importDialog.getByText("Loaded · 2 operations")).toBeVisible();
    // Step 1 picks the operations: GET ones start picked, the POST one waits
    // to be turned on. The spec names its server, so no Base URL is asked.
    await expect(importDialog.getByRole("checkbox", { name: "get_item" })).toBeChecked();
    await expect(importDialog.getByRole("checkbox", { name: "create_item" })).not.toBeChecked();
    await expect(importDialog.getByLabel("Base URL")).toHaveCount(0);
    await importDialog.getByRole("button", { name: "Review 1 tool" }).click();
    // Step 2 reads the group back, with the base URL the spec carried.
    await expect(importDialog.getByText(upstreamUrl, { exact: true })).toBeVisible();
    await importDialog.getByRole("button", { name: "Create group with 1 tool" }).click();

    await expect(page).toHaveURL(new RegExp(`/custom-tools/${name}$`));
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
    await expect(page.getByText("Imported from OpenAPI")).toBeVisible();
    // Overview, the bare address, holds the definition; the table is on Tools.
    await page.getByRole("tab", { name: "Tools" }).click();
    await expect(page).toHaveURL(new RegExp(`/custom-tools/${name}/tools$`));
    const tools = page.getByRole("region", { name: "Tools", exact: true });
    await expect(tools.getByRole("switch", { name: "Turn get_item on or off" })).toBeChecked();
    await expect(tools.getByText("GET /items/{id}")).toBeVisible();

    await tools.getByText("get_item", { exact: true }).click();
    const drawer = page.getByRole("dialog");
    await drawer.getByLabel("Value for id").fill("7");
    await drawer.getByRole("button", { name: "Run" }).click();
    const result = drawer.getByTestId("custom-tool-test-result");
    await expect(result).toContainText("200 OK");
    // The response sits in the viewer under the status block, indented.
    await expect(drawer.getByTestId("custom-tool-response")).toContainText(
      /"id":\s*"7"/,
    );
    await expect(page).toHaveURL(new RegExp(`/custom-tools/${name}/tools$`));
  } finally {
    await deleteGroup(name);
  }
});

test("a group made over REST is listed on Custom tools and left off MCP servers", async ({
  page,
}) => {
  const name = groupName("ctrest");
  const created = await api("POST", "/custom-tools", {
    name,
    base_url: upstreamUrl,
    tools: [
      {
        name: "get_item",
        description: "Read one item",
        method: "GET",
        path: "/items/{id}",
        input_schema: {
          type: "object",
          properties: { id: { type: "string" } },
          required: ["id"],
        },
      },
    ],
  });
  expect(created.status).toBe(201);
  try {
    await page.goto("/custom-tools");
    const healthy = page.getByRole("region", { name: "Healthy" });
    await expect(healthy.getByText(name, { exact: true })).toBeVisible();

    await page.goto("/mcp-servers");
    await expect(page.getByRole("heading", { level: 1, name: "MCP servers" })).toBeVisible();
    await expect(page.getByText(name, { exact: true })).toHaveCount(0);

    // Its MCP-server address opens its Custom tools page.
    await page.goto(`/mcp-servers/${name}`);
    await expect(page).toHaveURL(new RegExp(`/custom-tools/${name}$`));

    // A tool's switch, on the Tools tab, saves at once.
    await page.getByRole("tab", { name: "Tools" }).click();
    await page
      .getByRole("switch", { name: "Turn get_item on or off" })
      .click();
    await expect
      .poll(async () => {
        const group = (await (await api("GET", `/custom-tools/${name}`)).json()) as {
          tools: { name: string; enabled: boolean }[];
        };
        return group.tools[0].enabled;
      })
      .toBe(false);
  } finally {
    await deleteGroup(name);
  }
});
