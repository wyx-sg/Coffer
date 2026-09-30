// src/components/agents/list/AgentConfigDirDialog.test.tsx — picking, checking and applying a different config directory.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { AgentConfigDirDialog } from "./AgentConfigDirDialog";
import {
  fakeCallFor,
  fakeClientFor,
  fakeDaemon,
  typeRow,
  type FakeDaemon,
} from "./fakeAgentsDaemon";
import { renderWithDaemon } from "./renderWithDaemon";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

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

const HOME = "/Users/me/work/claude-home";

afterEach(() => vi.clearAllMocks());

describe("AgentConfigDirDialog", () => {
  acceptance(
    "agent-registry",
    "pick a custom config directory with the native dialog",
    async () => {
      const row = typeRow({ type: "claude_code" });
      const d = use(
        fakeDaemon({
          types: [row],
          pick: { available: true, path: HOME },
          folders: { [HOME]: ["skills"], [`${HOME}/skills`]: ["pdf", "release"] },
        }),
      );
      const onOpenChange = vi.fn();
      renderWithDaemon(<AgentConfigDirDialog row={row} open onOpenChange={onOpenChange} />);
      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByText(/Coffer looks in ~\/\.claude unless/)).toBeInTheDocument();

      fireEvent.click(within(dialog).getByRole("button", { name: /choose/i }));
      await waitFor(() => expect(screen.getByDisplayValue(HOME)).toBeInTheDocument());
      // The native dialog answered, so the in-app folder browser never opened.
      expect(screen.getAllByRole("dialog")).toHaveLength(1);
      expect(d.calls.some((c) => c.path === "/fs/pick-folder")).toBe(true);

      // What the folder holds, as far as the daemon shows folders.
      await waitFor(() => expect(within(dialog).getByText("2 skill folders")).toBeInTheDocument());
      expect(
        within(dialog).getByText(/writes its entry to ~\/work\/claude-home\/\.claude\.json/),
      ).toBeInTheDocument();

      fireEvent.click(within(dialog).getByRole("button", { name: "Use this directory" }));
      await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
      const register = d.calls.find((c) => c.method === "POST" && c.path === "/agents");
      expect(register?.body).toEqual({ type: "claude_code", config_dir: HOME });
      // Registering there does not connect it.
      expect(
        d.calls.some((c) => c.path.endsWith("/coffer-connection") && c.method === "POST"),
      ).toBe(false);
    },
  );

  test("an added agent's directory moves, and the daemon's refusal shows inline", async () => {
    const row = typeRow({ type: "codex", uid: "agt_c" });
    const d = use(fakeDaemon({ types: [row], folders: { "/Users/me/codex-2": [] } }));
    d.fail = (c) =>
      c.method === "PATCH"
        ? new ApiError("AGENT_CONFIG_DIR_TAKEN", "already registered")
        : undefined;
    const onOpenChange = vi.fn();
    renderWithDaemon(<AgentConfigDirDialog row={row} open onOpenChange={onOpenChange} />);
    const input = screen.getByLabelText("Config directory");
    fireEvent.change(input, { target: { value: "/Users/me/codex-2" } });
    await waitFor(() => expect(screen.getAllByText("Not here").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "Use this directory" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const patch = d.calls.find((c) => c.method === "PATCH");
    expect(patch).toMatchObject({
      path: "/agents/agt_c",
      body: { config_dir: "/Users/me/codex-2" },
    });
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
