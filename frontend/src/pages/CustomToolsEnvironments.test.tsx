// src/pages/CustomToolsEnvironments.test.tsx — a group's environments on the Custom tools page: the Environments
// section (one row per environment, switch, add, delete) and the environment picker in a tool's Test panel, which
// names the environment on every run (spec mcp-gateway "Choose a custom tool's environment on every call").
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { makeGroup, makeTool } from "@/components/custom-tools/testFixtures";
import type { CustomToolEnvironment, CustomToolGroup } from "@/lib/api/customTools";
import { api, renderAt, resetCustomToolMocks } from "./customToolsTestHarness";

vi.mock("@/lib/api/mcpServers", () => ({
  mcpServersApi: Object.fromEntries(
    ["summary", "tiering", "setToolExposure"].map((name) => [name, vi.fn()]),
  ),
}));
vi.mock("@/lib/api/customTools", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/customTools")>()),
  customToolsApi: Object.fromEntries(
    [
      "list",
      "get",
      "create",
      "update",
      "remove",
      "addTool",
      "updateTool",
      "removeTool",
      "test",
      "testUnsaved",
      "addEnvironment",
      "updateEnvironment",
      "removeEnvironment",
    ].map((name) => [name, vi.fn()]),
  ),
}));
vi.mock("@/lib/api/secret", () => ({ secretsApi: { list: vi.fn(async () => ({ refs: [] })) } }));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));

function environment(name: string, overrides: Partial<CustomToolEnvironment> = {}) {
  return {
    name,
    description: "",
    enabled: true,
    base_url: `https://${name}.billing.example/v2`,
    headers: [],
    variables: {},
    timeout_seconds: null,
    secret_state: "none",
    pending_approvals: [],
    pending_secrets: [],
    ...overrides,
  } as CustomToolEnvironment;
}

let group: CustomToolGroup;

beforeEach(() => {
  resetCustomToolMocks();
  group = makeGroup({
    name: "billing",
    headers: [],
    tools: [makeTool({ name: "get_invoice" })],
  });
  group = {
    ...group,
    environments: [
      environment("test", { variables: { region: "eu-1" } }),
      environment("live", { secret_state: "pending_approval" }),
    ],
  };
  api.list.mockResolvedValue([group]);
  api.get.mockResolvedValue(group);
  api.updateEnvironment.mockResolvedValue(group);
  api.removeEnvironment.mockResolvedValue(group);
  api.addEnvironment.mockResolvedValue(group);
});

describe("custom-tool environments", () => {
  test("the Overview lists every environment with its state, and a switch turns one off", async () => {
    renderAt("/custom-tools/billing");
    const section = await screen.findByRole("region", { name: "Environments" });
    const test_ = within(section).getByTestId("environment-test");
    const live = within(section).getByTestId("environment-live");
    expect(within(test_).getByText("https://test.billing.example/v2")).toBeInTheDocument();
    expect(within(test_).getByText("region=eu-1")).toBeInTheDocument();
    expect(within(live).getByText("Waiting for approval")).toBeInTheDocument();

    fireEvent.click(within(live).getByRole("switch", { name: "Environment live on" }));
    await waitFor(() =>
      expect(api.updateEnvironment).toHaveBeenCalledWith("billing", "live", { enabled: false }),
    );
  });

  test("adding an environment sends its name, base URL and variables", async () => {
    renderAt("/custom-tools/billing");
    const section = await screen.findByRole("region", { name: "Environments" });
    fireEvent.click(within(section).getByRole("button", { name: "Add environment" }));
    const dialog = await screen.findByRole("dialog", { name: "Add an environment to billing" });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "uat" } });
    fireEvent.change(within(dialog).getByLabelText(/^Base URL/), {
      target: { value: "https://uat.billing.example/v2" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.addEnvironment).toHaveBeenCalledWith(
        "billing",
        expect.objectContaining({ name: "uat", base_url: "https://uat.billing.example/v2" }),
      ),
    );
  });

  test("deleting an environment asks first", async () => {
    renderAt("/custom-tools/billing");
    const section = await screen.findByRole("region", { name: "Environments" });
    fireEvent.click(within(section).getByRole("button", { name: "Delete test" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete environment test?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete environment" }));
    await waitFor(() => expect(api.removeEnvironment).toHaveBeenCalledWith("billing", "test"));
  });

  test("a group's only environment has no Delete", async () => {
    const single = { ...group, environments: [environment("default")] };
    api.list.mockResolvedValue([single]);
    api.get.mockResolvedValue(single);
    renderAt("/custom-tools/billing");
    const section = await screen.findByRole("region", { name: "Environments" });
    expect(within(section).getByRole("button", { name: "Delete default" })).toBeDisabled();
  });

  test("the Test panel names the environment it runs in, and the result says where it ran", async () => {
    api.test.mockResolvedValue({
      ok: true,
      duration_ms: 90,
      url: "https://test.billing.example/v2/invoices/7",
      status: 200,
      status_line: "HTTP 200 OK",
      body: "{}",
      truncated: false,
      content_type: "application/json",
      error: null,
      failure: null,
      environment: "test",
    });
    renderAt("/custom-tools/billing/tools");
    const tools = await screen.findByRole("region", { name: "Tools" });
    fireEvent.click(within(tools).getByText("get_invoice"));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByRole("combobox", { name: "Environment" })).toHaveTextContent("test");
    fireEvent.change(within(drawer).getByLabelText("Value for id"), { target: { value: "7" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Run" }));
    expect(await within(drawer).findByText("Ran in test")).toBeInTheDocument();
    expect(api.test).toHaveBeenCalledWith(
      "billing",
      expect.objectContaining({ name: "get_invoice" }),
      { id: "7" },
      "test",
    );
  });
});
