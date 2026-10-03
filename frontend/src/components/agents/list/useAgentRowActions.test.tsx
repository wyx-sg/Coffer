// src/components/agents/list/useAgentRowActions.test.tsx — the visible fix a state calls for, the ⋯ menu order, and the enable flow.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ActionMenu } from "@/components/ui/menu";
import { acceptance } from "@/test/acceptance";
import { fakeApi } from "@/test/fakeApi";
import type { AgentTypeOut } from "@/lib/api/agents";
import { fakeCallFor, fakeDaemon, typeRow, type FakeDaemon } from "./fakeAgentsDaemon";
import { renderWithDaemon } from "./renderWithDaemon";
import { useAgentRowActions } from "./useAgentRowActions";

const call = fakeApi();

function use(d: FakeDaemon) {
  call.mockImplementation(fakeCallFor(d));
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
  test("a connected agent has no visible button; ⋯ lists Disconnect… and Turn off, never Remove", async () => {
    const row = typeRow({ type: "claude_code", uid: "agt_a" });
    const d = use(
      fakeDaemon({
        types: [row],
        connections: {
          agt_a: {
            state: "connected",
            parts: [{ key: "mcp", installed: true, detail: "/bin/coffer" }],
          },
        },
      }),
    );
    renderWithDaemon(<Harness row={row} />);
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("connected"));
    expect(screen.queryByRole("button", { name: /disconnect|repair|connect/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "menu" }));
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.textContent),
    ).toEqual([
      "Use a different config directory…",
      "Reveal config directory",
      "Copy uid",
      "Disconnect…",
      "Turn off",
    ]);
    // Disconnect… goes through Review changes; nothing is written before Apply.
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Disconnect…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Disconnect Claude Code from Coffer?")).toBeInTheDocument();
    expect(writes(d)).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(writes(d)).toEqual(["DELETE /agents/agt_a/coffer-connection"]));
  });

  test("a partial connection offers Repair as its one button, and Disconnect… stays in ⋯", async () => {
    const row = typeRow({ type: "codex", uid: "agt_c" });
    use(
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
    const items = within(await screen.findByRole("menu")).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toContain("Disconnect…");
    expect(items.map((i) => i.textContent)).not.toContain("Remove from Coffer");
  });

  test("a disconnected or newly found agent reads one off state with Connect", async () => {
    const added = typeRow({ type: "claude_code", uid: "agt_a" });
    use(fakeDaemon({ types: [added] }));
    const first = renderWithDaemon(<Harness row={added} />);
    expect(await screen.findByRole("button", { name: "Connect" })).toBeInTheDocument();
    first.unmount();

    const found = typeRow({ type: "codex" });
    use(fakeDaemon({ types: [found] }));
    renderWithDaemon(<Harness row={found} />);
    expect(await screen.findByRole("button", { name: "Connect" })).toBeInTheDocument();
  });

  test("the menu does not repeat the visible button: no Turn on on a disabled agent", async () => {
    const row = typeRow({ type: "claude_code", uid: "agt_a" });
    use(fakeDaemon({ types: [row], disabled: ["agt_a"] }));
    renderWithDaemon(<Harness row={row} />);
    await screen.findByRole("button", { name: "Turn on" });
    fireEvent.click(screen.getByRole("button", { name: "menu" }));
    const items = within(await screen.findByRole("menu")).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).not.toContain("Turn on");
  });

  test("a disabled agent offers Turn on, which switches it back on", async () => {
    const row = typeRow({ type: "claude_code", uid: "agt_a" });
    const d = use(fakeDaemon({ types: [row], disabled: ["agt_a"] }));
    renderWithDaemon(<Harness row={row} />);
    const enable = await screen.findByRole("button", { name: "Turn on" });
    fireEvent.click(enable);
    await waitFor(() => expect(writes(d)).toEqual(["POST /resources/agt_a/enable"]));
    await waitFor(() => expect(screen.getByTestId("state")).not.toHaveTextContent("disabled"));
  });

  acceptance(
    "web-ui",
    "an agent whose program is not found offers its install prompt",
    async () => {
      const row = typeRow({
        type: "codex",
        state: "missing",
        addable: false,
        version: null,
        install_handoff: { prompt: "Please install OpenAI Codex on this machine." },
      });
      use(fakeDaemon({ types: [row] }));
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });
      renderWithDaemon(<Harness row={row} />);
      // No visible button: Copy prompt heads the ⋯ menu, apart from the rest.
      expect(screen.queryByRole("button", { name: "Copy prompt" })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "menu" }));
      const menu = await screen.findByRole("menu");
      // No managed agent is available, so the menu has no Ask an agent.
      expect(
        within(menu)
          .getAllByRole("menuitem")
          .map((i) => i.textContent),
      ).toEqual(["Copy prompt", "Use a different config directory…"]);
      expect(within(menu).getByRole("separator")).toBeInTheDocument();
      // The daemon's prompt, copied as given; no install command anywhere.
      fireEvent.click(within(menu).getByRole("menuitem", { name: "Copy prompt" }));
      expect(writeText).toHaveBeenCalledWith("Please install OpenAI Codex on this machine.");
      expect(document.body).not.toHaveTextContent(/npm|install -g/);
    },
  );

  acceptance(
    "web-ui",
    "ask an agent is offered only while another managed agent is available",
    async () => {
      const row = typeRow({
        type: "claude_code",
        state: "config_only",
        addable: false,
        version: null,
        install_handoff: { prompt: "Please reinstall Claude Code on this machine." },
      });
      // The missing agent itself cannot run a turn; Codex can.
      const d = use(
        fakeDaemon({
          types: [row],
          providers: [
            { agent_key: "claude_code", display_name: "Claude Code", available: false },
            { agent_key: "codex", display_name: "Codex", available: true },
          ],
        }),
      );
      renderWithDaemon(<Harness row={row} />);
      fireEvent.click(screen.getByRole("button", { name: "menu" }));
      const ask = await within(await screen.findByRole("menu")).findByRole("menuitem", {
        name: "Ask an agent",
      });
      fireEvent.click(ask);
      // Straight to the draft: no dialog, and nothing written.
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(writes(d)).toEqual([]);
    },
  );

  test("with only the missing agent itself managed, Ask an agent is not offered", async () => {
    const row = typeRow({
      type: "claude_code",
      state: "config_only",
      addable: false,
      version: null,
      install_handoff: { prompt: "Please reinstall Claude Code on this machine." },
    });
    use(
      fakeDaemon({
        types: [row],
        providers: [{ agent_key: "claude_code", display_name: "Claude Code", available: false }],
      }),
    );
    renderWithDaemon(<Harness row={row} />);
    fireEvent.click(await screen.findByRole("button", { name: "menu" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "Copy prompt" })).toBeInTheDocument();
    expect(within(menu).queryByRole("menuitem", { name: "Ask an agent" })).toBeNull();
  });
});
