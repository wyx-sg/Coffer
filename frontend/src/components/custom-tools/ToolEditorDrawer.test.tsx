// src/components/custom-tools/ToolEditorDrawer.test.tsx — the tool drawer previews and tests in ONE environment:
// the request help, the headers, the preview's URL, secret and timeout, and the run all follow the test's picker;
// picking saves nothing; an environment switched off or deleted is reported, never replaced by another.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import type { CustomToolEnvironment, CustomToolGroup } from "@/lib/api/customTools";
import { customToolsApi } from "@/lib/api/customTools";
import { acceptance } from "@/test/acceptance";
import { ToolEditorDrawer } from "./ToolEditorDrawer";
import { makeGroup, makeTool } from "./testFixtures";

vi.mock("@/lib/api/customTools", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/customTools")>()),
  customToolsApi: {
    test: vi.fn(),
    update: vi.fn(),
    updateTool: vi.fn(),
    deleteTool: vi.fn(),
    updateEnvironment: vi.fn(),
    get: vi.fn(),
    list: vi.fn(),
  },
}));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [
        {
          ref: "secret/test-key",
          label: "test-key",
          present: true,
          locked: false,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
  },
}));

const api = customToolsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

function env(overrides: Partial<CustomToolEnvironment>): CustomToolEnvironment {
  return {
    name: "test",
    description: "",
    enabled: true,
    base_url: "https://test.example/api",
    headers: [],
    variables: {},
    timeout_seconds: null,
    secret_state: "none",
    pending_approvals: [],
    pending_secrets: [],
    rejected_approvals: [],
    rejected_secrets: [],
    ...overrides,
  };
}

const TEST = env({
  name: "test",
  headers: [
    {
      name: "Authorization",
      value: null,
      scheme: "Bearer",
      secret: "test-key",
      secret_state: "present",
    },
    { name: "X-Tenant", value: "tenant-test", scheme: null, secret: null, secret_state: "none" },
  ],
  variables: { region: "eu-1" },
  secret_state: "present",
});
const LIVE = env({
  name: "live",
  base_url: "https://live.example/api",
  headers: [
    { name: "X-Tenant", value: "tenant-live", scheme: null, secret: null, secret_state: "none" },
  ],
  variables: { region: "us-1" },
  timeout_seconds: 7,
});

function groupWith(environments: CustomToolEnvironment[]): CustomToolGroup {
  return makeGroup({
    base_url: TEST.base_url,
    headers: TEST.headers,
    environments,
    tools: [
      makeTool({
        name: "items",
        path: "/v1/{env:region}/items/{id}",
        headers: { "X-Client": "c-{env:region}" },
      }),
    ],
  });
}

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function wrap(node: ReactNode, qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  );
}

function drawer(group: CustomToolGroup) {
  return (
    <ToolEditorDrawer group={group} toolName="items" open onClose={vi.fn()} onEditGroup={vi.fn()} />
  );
}

const preview = () => screen.getByTestId("custom-tool-request-preview");

async function pick(name: string) {
  const select = screen.getByRole("combobox", { name: "Environment" });
  fireEvent.keyDown(select, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name }));
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset();
  api.test.mockResolvedValue({
    ok: true,
    duration_ms: 12,
    url: "https://live.example/api/v1/us-1/items/7",
    status: 200,
    status_line: "HTTP 200 OK",
    body: "{}",
    truncated: false,
    content_type: "application/json",
    error: null,
    failure: null,
    handoff: null,
    environment: "live",
    response_headers: { "x-request-id": "req-9" },
  });
});

describe("ToolEditorDrawer environment", () => {
  acceptance("web-ui", "the tool form previews and tests in the environment it names", async () => {
    render(wrap(drawer(groupWith([TEST, LIVE])), client()));

    expect(screen.getByText("Added to test's base URL https://test.example/api.")).toBeVisible();
    expect(
      within(preview()).getByText("https://test.example/api/v1/eu-1/items/{id}"),
    ).toBeVisible();
    expect(within(preview()).getByText("X-Tenant: tenant-test")).toBeVisible();
    expect(within(preview()).getByText("X-Client: c-eu-1")).toBeVisible();
    expect(await within(preview()).findByText("test-key")).toBeVisible();
    expect(within(preview()).getByText("Timeout 30 s (the group's)")).toBeVisible();

    await pick("live");

    expect(screen.getByText("Added to live's base URL https://live.example/api.")).toBeVisible();
    expect(
      within(preview()).getByText("https://live.example/api/v1/us-1/items/{id}"),
    ).toBeVisible();
    expect(within(preview()).getByText("X-Tenant: tenant-live")).toBeVisible();
    expect(within(preview()).getByText("Timeout 7 s (live's own)")).toBeVisible();
    // live has no secret header: no other environment's secret shows anywhere in the form.
    expect(screen.queryByText("test-key")).toBeNull();
    expect(screen.queryByText("Authorization")).toBeNull();

    fireEvent.change(screen.getByLabelText("Value for id"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(api.test).toHaveBeenCalledTimes(1));
    expect(api.test.mock.calls[0][0]).toBe("billing");
    expect(api.test.mock.calls[0][3]).toBe("live");
    expect(await screen.findByText("x-request-id: req-9")).toBeVisible();
    // Picking and running changed nothing saved.
    for (const write of ["update", "updateTool", "updateEnvironment", "deleteTool"])
      expect(api[write]).not.toHaveBeenCalled();
  });

  acceptance("web-ui", "a tool form never runs in an environment that is off or gone", async () => {
    const qc = client();
    const { rerender } = render(wrap(drawer(groupWith([TEST, LIVE])), qc));
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();

    rerender(wrap(drawer(groupWith([{ ...TEST, enabled: false }, LIVE])), qc));
    expect(
      screen.getByText(
        "Environment test is off, so nothing runs. Pick one that is on, or turn it back on under Environments.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
    expect(screen.queryByTestId("custom-tool-request-preview")).toBeNull();

    rerender(wrap(drawer(groupWith([LIVE])), qc));
    expect(
      screen.getByText("Environment test was deleted, so nothing runs. Pick another environment."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();

    await pick("live");
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
    expect(api.test).not.toHaveBeenCalled();
  });

  test("a group with no environment on says so and runs nothing", () => {
    render(wrap(drawer(groupWith([{ ...TEST, enabled: false }])), client()));
    expect(
      screen.getByText(
        "No environment of this group is on, so nothing runs. Turn one on under Environments.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
    expect(
      screen.getByText("Added to the base URL of the environment the request runs in."),
    ).toBeVisible();
  });
});
