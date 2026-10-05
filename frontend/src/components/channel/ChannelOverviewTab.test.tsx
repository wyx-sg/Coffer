// src/components/channel/ChannelOverviewTab.test.tsx — the Default model row:
// it lists the default agent's catalogue (by label, stored by id) behind a
// "Provider default" entry, and shows a stored id the catalogue lacks as itself.
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ChannelOverviewTab } from "./ChannelOverviewTab";
import type { ResourceOut } from "@/lib/api/resources";
import { fakeApi } from "@/test/fakeApi";

const callMock = fakeApi();

vi.mock("@/components/ScopeControl", () => ({ ScopeControl: () => null }));

const AGENT = {
  uid: "u-cc",
  name: "claude-code",
  type: "claude_code",
  display_name: "Claude Code",
  config_dir: "/h/.claude",
  state: "installed_active",
};

beforeEach(() => {
  callMock.mockImplementation(async (path: string) => {
    const p = path.split("?")[0];
    if (p === "/agents") return { items: [AGENT] };
    if (p === "/agents/u-cc") return AGENT;
    if (p === "/agent-providers/claude_code/models")
      return {
        default_model: null,
        models: [{ id: "opus", label: "Opus 5", description: "" }],
      };
    return { items: [] };
  });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderTab(agentConfig: Record<string, unknown> | null) {
  const channel = {
    uid: "ch1",
    enabled: true,
    config: { default_agent: "u-cc", default_agent_config: agentConfig },
  } as unknown as ResourceOut;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  render(
    <ChannelOverviewTab
      channel={channel}
      status={undefined}
      onAdd={vi.fn()}
      onRemove={vi.fn()}
      onDefaultAgentChange={vi.fn()}
      onDefaultModelChange={vi.fn()}
    />,
    { wrapper: Wrapper },
  );
}

describe("ChannelOverviewTab — Default model", () => {
  test("no stored model reads Provider default", async () => {
    renderTab({ cwd: "/w" });
    const trigger = await screen.findByRole("combobox", { name: "Default model" });
    expect(trigger).toHaveTextContent("Provider default");
  });

  test("a stored id shows its catalogue label", async () => {
    renderTab({ model: "opus" });
    const trigger = await screen.findByRole("combobox", { name: "Default model" });
    await vi.waitFor(() => expect(trigger).toHaveTextContent("Opus 5"));
  });

  test("a stored id missing from the catalogue shows as itself", async () => {
    renderTab({ model: "retired-model" });
    const trigger = await screen.findByRole("combobox", { name: "Default model" });
    expect(trigger).toHaveTextContent("retired-model");
  });
});
