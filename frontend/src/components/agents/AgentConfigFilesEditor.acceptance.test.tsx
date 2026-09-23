// frontend/src/components/agents/AgentConfigFilesEditor.acceptance.test.tsx
// Acceptance scenarios for the Config files tab of spec agent-registry: the
// daemon-backed open / reveal pair beside a selected file, and the annotation
// on an instructions file that still carries the retired memory block.
import { afterEach, describe, expect, vi, type Mock } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";

import { AgentConfigFilesEditor } from "./AgentConfigFilesEditor";
import { fsApi } from "@/lib/api/fs";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentConfigFiles: vi.fn(),
  useAgentConfigFile: vi.fn(),
  useAgentConfigChild: vi.fn(),
}));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));

const { useAgentConfigFiles, useAgentConfigFile, useAgentConfigChild } =
  await import("@/lib/hooks/useAgents");

const INSTRUCTIONS = {
  key: "instructions",
  display_name: "Instructions",
  path: "/home/u/.claude/CLAUDE.md",
  folder_path: "/home/u/.claude",
  format: "markdown" as const,
  exists: true,
  size: 40,
  modified_at: "2026-06-01T00:00:00Z",
};

function stub(memoryBlock: boolean) {
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
      path: INSTRUCTIONS.path,
      folder_path: INSTRUCTIONS.folder_path,
      memory_block: memoryBlock,
    },
    isPending: false,
  } as unknown as ReturnType<typeof useAgentConfigFile>);
  vi.mocked(useAgentConfigChild).mockReturnValue({
    data: undefined,
    isPending: false,
  } as unknown as ReturnType<typeof useAgentConfigChild>);
}

function renderEditor(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Config files tab — acceptance", () => {
  acceptance("agent-registry", "open a config file and reveal it through the daemon", async () => {
    (fsApi.open as Mock).mockResolvedValue(undefined);
    (fsApi.reveal as Mock).mockResolvedValue(undefined);
    stub(false);
    renderEditor(<AgentConfigFilesEditor uid="u-cc" />);
    fireEvent.click(screen.getByText("Instructions"));

    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(INSTRUCTIONS.path, undefined));
    fireEvent.click(screen.getByRole("button", { name: /reveal/i }));
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(INSTRUCTIONS.path));

    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
  });

  acceptance("agent-registry", "annotate a leftover memory block in the instructions file", () => {
    stub(true);
    renderEditor(<AgentConfigFilesEditor uid="u-cc" />);
    fireEvent.click(screen.getByText("Instructions"));

    expect(screen.getByText(/legacy Coffer memory block/i)).toBeInTheDocument();
  });

  acceptance("agent-registry", "annotate a leftover memory block in the instructions file", () => {
    // The annotation follows the read's flag — a clean file carries none.
    stub(false);
    renderEditor(<AgentConfigFilesEditor uid="u-cc" />);
    fireEvent.click(screen.getByText("Instructions"));

    expect(screen.queryByText(/legacy Coffer memory block/i)).toBeNull();
  });
});
