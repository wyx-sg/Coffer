// src/components/agents/list/useAgentRowActions.test.tsx — the action a state calls for, and the remove and enable flows.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ActionMenu } from "@/components/ui/menu";
import type { AgentTypeOut } from "@/lib/api/agents";
import {
  fakeCallFor,
  fakeClientFor,
  fakeDaemon,
  typeRow,
  type FakeDaemon,
} from "./fakeAgentsDaemon";
import { renderWithDaemon } from "./renderWithDaemon";
import { useAgentRowActions } from "./useAgentRowActions";

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

/** What the detail page does with the hook: a primary button, a menu, the dialogs. */
function Harness({ row }: { row: AgentTypeOut }) {
  const { state, primary, actions, dialogs } = useAgentRowActions(row);
  return (
    <div>
      <span data-testid="state">{state}</span>
      {primary ? <button onClick={primary.run}>{primary.label}</button> : null}
      <ActionMenu label="menu" actions={actions} />
      {dialogs}
    </div>
  );
}

const writes = (d: FakeDaemon) =>
  d.calls.filter((c) => c.method !== "GET").map((c) => `${c.method} ${c.path}`);

afterEach(() => vi.clearAllMocks());

describe("useAgentRowActions", () => {
  test("Remove from Coffer takes Coffer's parts out before removing the agent", async () => {
    const row = typeRow({ type: "codex", uid: "agt_c" });
    const d = use(
      fakeDaemon({
        types: [row],
        connections: {
          agt_c: {
            state: "partial",
            parts: [{ key: "mcp", installed: true, detail: "/bin/coffer" }],
          },
        },
      }),
    );
    renderWithDaemon(<Harness row={row} />);
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("needs_repair"));
    expect(screen.getByRole("button", { name: "Repair" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "menu" }));
    const menu = await screen.findByRole("menu");
    // No Open item without includeOpen — the detail header already is the agent.
    expect(within(menu).queryByText("Open")).not.toBeInTheDocument();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Remove from Coffer" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Remove Codex from Coffer?")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Coffer takes its entry and hook out of ~/.codex");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(writes(d)).toEqual(["DELETE /agents/agt_c/coffer-connection", "DELETE /agents/agt_c"]),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("a disabled agent offers Enable, which switches it back on", async () => {
    const row = typeRow({ type: "claude_code", uid: "agt_a" });
    const d = use(fakeDaemon({ types: [row], disabled: ["agt_a"] }));
    renderWithDaemon(<Harness row={row} />);
    const enable = await screen.findByRole("button", { name: "Enable" });
    fireEvent.click(enable);
    await waitFor(() => expect(writes(d)).toEqual(["POST /resources/agt_a/enable"]));
    await waitFor(() => expect(screen.getByTestId("state")).not.toHaveTextContent("disabled"));
  });

  test("a type not installed offers the install command and a menu without agent items", async () => {
    const row = typeRow({ type: "codex", state: "missing", addable: false, version: null });
    use(fakeDaemon({ types: [row] }));
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderWithDaemon(<Harness row={row} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy command" }));
    expect(writeText).toHaveBeenCalledWith("npm install -g @openai/codex");
    fireEvent.click(screen.getByRole("button", { name: "menu" }));
    const items = within(await screen.findByRole("menu")).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual(["Use a different config directory…"]);
  });
});
