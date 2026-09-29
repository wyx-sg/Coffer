// src/components/agents/connect/AgentConnectionChangeDialog.test.tsx — disconnect, idempotent connect and the memory switch.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import {
  AgentConnectionChangeDialog,
  type ConnectionChangeRequest,
} from "./AgentConnectionChangeDialog";
import {
  fakeCallFor,
  fakeClientFor,
  fakeDaemon,
  typeRow,
  type FakeDaemon,
} from "@/components/agents/list/fakeAgentsDaemon";
import { renderWithDaemon } from "@/components/agents/list/renderWithDaemon";

vi.mock("@/lib/api/call", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/call")>()),
  call: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { call } = await import("@/lib/api/call");
const { getApiClient } = await import("@/lib/api/client");

function use(d: FakeDaemon) {
  vi.mocked(call).mockImplementation(fakeCallFor(d) as never);
  vi.mocked(getApiClient).mockReturnValue(fakeClientFor(d) as never);
  return d;
}

const claude = typeRow({ type: "claude_code", uid: "agt_a" });
const both = [
  { key: "mcp", installed: true, detail: "/Users/me/.coffer/bin/coffer" },
  { key: "memory_hook", installed: true, detail: "coffer memory context --agent-uid agt_a" },
];

afterEach(() => vi.clearAllMocks());

describe("AgentConnectionChangeDialog", () => {
  test("disconnect names itself, lists Coffer's lines as removed and confirms with Disconnect", async () => {
    const d = use(
      fakeDaemon({ types: [claude], connections: { agt_a: { state: "connected", parts: both } } }),
    );
    const onClose = vi.fn();
    const request: ConnectionChangeRequest = { kind: "disconnect", row: claude };
    renderWithDaemon(<AgentConnectionChangeDialog request={request} onClose={onClose} />);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByText("Disconnect Claude Code from Coffer?")).toBeInTheDocument(),
    );
    expect(within(dialog).getByText("Review changes")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Loses Coffer’s MCP servers, skills and memory/),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Only Coffer’s own lines are removed/)).toBeInTheDocument();
    expect(within(dialog).getAllByText("−4").length).toBeGreaterThan(0);
    expect(dialog.querySelectorAll('[data-line="remove"]').length).toBeGreaterThan(0);
    expect(d.calls.filter((c) => c.method !== "GET")).toEqual([]);

    fireEvent.click(within(dialog).getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(within(dialog).getByText("Changes applied")).toBeInTheDocument());
    expect(d.calls.filter((c) => c.method !== "GET").map((c) => `${c.method} ${c.path}`)).toEqual([
      "DELETE /agents/agt_a/coffer-connection",
    ]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalled();
  });

  test("connecting an agent that is already connected has nothing to change", async () => {
    use(
      fakeDaemon({ types: [claude], connections: { agt_a: { state: "connected", parts: both } } }),
    );
    renderWithDaemon(
      <AgentConnectionChangeDialog request={{ kind: "connect", row: claude }} onClose={() => {}} />,
    );
    expect(await screen.findByText("Nothing to change")).toBeInTheDocument();
  });

  test("with memory off, adding writes only the MCP entry", async () => {
    const codex = typeRow({ type: "codex" });
    use(fakeDaemon({ types: [codex], memoryOn: false }));
    renderWithDaemon(
      <AgentConnectionChangeDialog request={{ kind: "add", rows: [codex] }} onClose={() => {}} />,
    );
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByTestId("change-summary")).toHaveTextContent("1 change in 1 agent"),
    );
    expect(within(dialog).getAllByText("~/.codex/config.toml").length).toBeGreaterThan(0);
    expect(within(dialog).queryByText("~/.codex/hooks.json")).not.toBeInTheDocument();
    // Before registration the uid is not known, and the preview says so.
    expect(within(dialog).getByText(/<assigned on add>/)).toBeInTheDocument();
  });
});
