// src/components/agents/connect/AgentConnectionChangeDialog.test.tsx — disconnect, idempotent connect and the memory switch.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import {
  AgentConnectionChangeDialog,
  type ConnectionChangeRequest,
} from "./AgentConnectionChangeDialog";
import {
  fakeCallFor,
  fakeDaemon,
  typeRow,
  type FakeDaemon,
} from "@/components/agents/list/fakeAgentsDaemon";
import { renderWithDaemon } from "@/components/agents/list/renderWithDaemon";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import { fakeApi } from "@/test/fakeApi";

const call = fakeApi();

function use(d: FakeDaemon) {
  call.mockImplementation(fakeCallFor(d));
  return d;
}

const claude = typeRow({ type: "claude_code", uid: "agt_a" });
const both = [
  { key: "mcp", installed: true, detail: "/Users/me/.coffer/bin/coffer" },
  { key: "memory_hook", installed: true, detail: "coffer memory hook --agent-uid agt_a" },
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

  test("adding an agent writes the MCP entry and the memory hook", async () => {
    const codex = typeRow({ type: "codex" });
    use(fakeDaemon({ types: [codex] }));
    renderWithDaemon(
      <AgentConnectionChangeDialog request={{ kind: "add", rows: [codex] }} onClose={() => {}} />,
    );
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByTestId("changes-heading")).toHaveTextContent("Changes · 2"),
    );
    expect(within(dialog).getAllByText("~/.codex/config.toml").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("~/.codex/hooks.json").length).toBeGreaterThan(0);
    // Before registration the uid is not known, and both previews say so.
    expect(within(dialog).getAllByText(/<assigned on add>/)).toHaveLength(2);
  });

  acceptance(
    "web-ui",
    "a connect refused for a missing shim offers the daemon's prompt",
    async () => {
      const prompt = "Please find or reinstall Coffer's `coffer-mcp-shim` program on this machine.";
      use(
        fakeDaemon({
          types: [claude],
          connections: {
            agt_a: {
              state: "disconnected",
              parts: [
                { key: "mcp", installed: false, detail: null },
                { key: "memory_hook", installed: false, detail: null },
              ],
            },
          },
          fail: (c) =>
            c.method === "POST" && c.path === "/agents/agt_a/coffer-connection"
              ? new ApiError("SHIM_NOT_FOUND", "could not resolve the coffer-mcp-shim binary", {
                  handoff: { prompt },
                })
              : undefined,
        }),
      );
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });
      renderWithDaemon(
        <AgentConnectionChangeDialog
          request={{ kind: "connect", row: claude }}
          onClose={() => {}}
        />,
      );
      const dialog = await screen.findByRole("dialog");
      const apply = await within(dialog).findByRole("button", { name: /^Apply/ });
      fireEvent.click(apply);
      await waitFor(() =>
        expect(within(dialog).getByText("Some changes failed")).toBeInTheDocument(),
      );
      // The refusal's copy names no command or environment variable.
      expect(dialog).not.toHaveTextContent(/COFFER_MCP_SHIM_PATH|on PATH, or set/);
      fireEvent.click(within(dialog).getByRole("button", { name: "Copy prompt" }));
      expect(writeText).toHaveBeenCalledWith(prompt);
    },
  );
});
