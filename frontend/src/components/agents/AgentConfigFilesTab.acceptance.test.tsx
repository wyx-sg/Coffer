// frontend/src/components/agents/AgentConfigFilesTab.acceptance.test.tsx
// Acceptance scenarios for the Config files tab of spec agent-registry: the
// daemon-backed open / reveal pair beside a selected file.
import { afterEach, describe, expect, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentConfigFilesTab } from "./AgentConfigFilesTab";
import type { AgentOut } from "@/lib/api/agents";
import { fsApi } from "@/lib/api/fs";
import { acceptance } from "@/test/acceptance";
import "@/i18n";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentConfigFiles: vi.fn(),
  useAgentConfigFile: vi.fn(),
  useAgentConfigChild: vi.fn(),
}));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));

const { useAgentConfigFiles, useAgentConfigFile, useAgentConfigChild } =
  await import("@/lib/hooks/useAgents");

const AGENT = {
  uid: "u-cc",
  type: "claude_code",
  name: "claude_code",
  display_name: "Claude Code",
  config_dir: "/home/u/.claude",
} as AgentOut;

const INSTRUCTIONS = {
  key: "instructions",
  display_name: "User instructions (CLAUDE.md)",
  path: "/home/u/.claude/CLAUDE.md",
  folder_path: "/home/u/.claude",
  kind: "file" as const,
  format: "markdown" as const,
  exists: true,
  files: null,
  size: 40,
  modified_at: "2026-06-01T00:00:00Z",
};

function stub() {
  vi.mocked(useAgentConfigFiles).mockReturnValue({
    data: [INSTRUCTIONS],
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useAgentConfigFiles>);
  vi.mocked(useAgentConfigFile).mockReturnValue({
    data: {
      key: "instructions",
      format: "markdown",
      exists: true,
      content: "# Rules\n",
      fingerprint: "fp",
      path: INSTRUCTIONS.path,
      folder_path: INSTRUCTIONS.folder_path,
    },
    isPending: false,
  } as unknown as ReturnType<typeof useAgentConfigFile>);
  vi.mocked(useAgentConfigChild).mockReturnValue({
    data: undefined,
    isPending: false,
  } as unknown as ReturnType<typeof useAgentConfigChild>);
}

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Config files tab — acceptance", () => {
  acceptance("agent-registry", "open a config file and reveal it through the daemon", async () => {
    (fsApi.open as Mock).mockResolvedValue(undefined);
    (fsApi.reveal as Mock).mockResolvedValue(undefined);
    stub();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AgentConfigFilesTab agent={AGENT} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByText("CLAUDE.md"));

    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(INSTRUCTIONS.path, undefined));
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(INSTRUCTIONS.path));

    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
  });
});
