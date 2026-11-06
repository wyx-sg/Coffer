// e2e/web/specs/custom-tools.spec.ts
//
// The Custom tools page in a real browser against the isolated daemon (change
// revise-web-ui-ia, spec web-ui "Manage custom tool groups on their own page"): the
// group page with its tools, the tool drawer's Test calling a real upstream (a
// tiny HTTP server this spec starts on 127.0.0.1), and a group created over REST
// staying off the MCP servers page. Plain tests until the change is archived (its task 7.14d).

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

/** A group of one GET tool on the upstream, made over REST. */
async function makeItemsGroup(name: string): Promise<void> {
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
}

test("a group's tool is listed on its page, and its Test calls the API from the drawer", async ({
  page,
}) => {
  const name = groupName("cte2e");
  await makeItemsGroup(name);
  try {
    await page.goto(`/custom-tools/${name}`);
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
    // Overview, the bare address, holds the definition; the table is on Tools.
    await page.getByRole("tab", { name: "Tools" }).click();
    await expect(page).toHaveURL(new RegExp(`/custom-tools/${name}/tools$`));
    const tools = page.getByRole("region", { name: "Tools", exact: true });
    await expect(tools.getByRole("switch", { name: "Turn get_item on or off" })).toBeChecked();
    await expect(tools.getByText("/items/{id}", { exact: true })).toBeVisible();

    await tools.getByText("get_item", { exact: true }).click();
    const drawer = page.getByRole("dialog");
    // Test is the editor's last tab: sample values, the request to send, then the response.
    await drawer.getByRole("tab", { name: "Test" }).click();
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
  await makeItemsGroup(name);
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
