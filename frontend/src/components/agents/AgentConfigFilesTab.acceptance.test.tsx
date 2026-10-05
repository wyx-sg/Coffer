// frontend/src/components/agents/AgentConfigFilesTab.acceptance.test.tsx
// Acceptance scenarios for the Config files tab of spec agent-registry "Open
// config files in an external editor or reveal them": the daemon-backed open /
// reveal pair on the open file, a file not created yet marked and not
// previewable, no edit, new-file, delete or copy-path anywhere; and the
// read-only preview a selected file shows.
import { afterEach, describe, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentConfigFilesTab } from "./AgentConfigFilesTab";
import {
  agentsApi,
  type AgentOut,
  type ConfigFileContent,
  type ConfigFileInfo,
} from "@/lib/api/agents";
import { fsApi } from "@/lib/api/fs";
import { acceptance } from "@/test/acceptance";
import "@/i18n";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: { listConfigFiles: vi.fn(), configFileContent: vi.fn() },
}));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));

const AGENT = {
  uid: "u-cc",
  type: "claude_code",
  name: "claude_code",
  display_name: "Claude Code",
  config_dir: "/home/u/.claude",
} as AgentOut;

const INSTRUCTIONS: ConfigFileInfo = {
  key: "instructions",
  display_name: "User instructions (CLAUDE.md)",
  path: "/home/u/.claude/CLAUDE.md",
  folder_path: "/home/u/.claude",
  kind: "file",
  format: "markdown",
  exists: true,
  files: null,
  size: 40,
  modified_at: "2026-06-01T00:00:00Z",
};
const SETTINGS: ConfigFileInfo = {
  ...INSTRUCTIONS,
  key: "settings",
  display_name: "User settings",
  path: "/home/u/.claude/settings.json",
  format: "json",
  size: 70,
};
const LOCAL: ConfigFileInfo = {
  ...INSTRUCTIONS,
  key: "settings_local",
  display_name: "Local settings",
  path: "/home/u/.claude/settings.local.json",
  format: "json",
  exists: false,
  size: null,
  modified_at: null,
};

const INSTRUCTIONS_CONTENT: ConfigFileContent = {
  key: "instructions",
  abs_path: INSTRUCTIONS.path,
  format: "markdown",
  content: "Be terse.",
  size: 40,
  truncated: false,
  binary: false,
};

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AgentConfigFilesTab agent={AGENT} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Config files tab — acceptance", () => {
  acceptance("agent-registry", "open a config file and reveal it through the daemon", async () => {
    vi.mocked(agentsApi.listConfigFiles).mockResolvedValue({ items: [INSTRUCTIONS, LOCAL] });
    vi.mocked(agentsApi.configFileContent).mockResolvedValue(INSTRUCTIONS_CONTENT);
    vi.mocked(fsApi.open).mockResolvedValue(undefined);
    vi.mocked(fsApi.reveal).mockResolvedValue(undefined);
    renderTab();

    // The first existing file is open; the viewer's Open in editor and Reveal act on it.
    expect(await screen.findByText("Be terse.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open in editor" }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(INSTRUCTIONS.path, undefined));
    const reveals = screen.getAllByRole("button", { name: "Reveal in Finder" });
    fireEvent.click(reveals[reveals.length - 1]);
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(INSTRUCTIONS.path));

    // The file not created yet: marked, and selecting it opens nothing.
    const missing = screen.getByRole("treeitem", { name: /settings\.local\.json/ });
    expect(missing).toHaveTextContent("Not created");
    fireEvent.click(missing);
    expect(missing).toHaveAttribute("aria-selected", "false");
    expect(fsApi.open).toHaveBeenCalledTimes(1);
    expect(agentsApi.configFileContent).toHaveBeenCalledTimes(1);

    // Nothing offers a change, and there is no copy-path fallback.
    for (const name of [/^edit$/i, /save/i, /revert/i, /new file/i, /delete/i, /copy/i]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  acceptance("agent-registry", "preview a config file from its row", async () => {
    vi.mocked(agentsApi.listConfigFiles).mockResolvedValue({ items: [INSTRUCTIONS, SETTINGS] });
    vi.mocked(agentsApi.configFileContent).mockImplementation(async (_uid, key) =>
      key === "settings"
        ? ({
            key: "settings",
            abs_path: SETTINGS.path,
            format: "json",
            content: '{\n  "theme": "dark",\n  "model": "opus"\n}\n',
            size: 70,
            truncated: false,
            binary: false,
          } satisfies ConfigFileContent)
        : INSTRUCTIONS_CONTENT,
    );
    renderTab();

    fireEvent.click(await screen.findByRole("treeitem", { name: /settings\.json/ }));
    await waitFor(() => expect(screen.getByText(/"model"/)).toBeInTheDocument());
    expect(agentsApi.configFileContent).toHaveBeenCalledWith("u-cc", "settings", undefined);
    expect(screen.getByText(/"theme"/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open in editor" })).toBeInTheDocument();
    for (const name of [/^edit$/i, /save/i, /revert/i]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
  });
});
