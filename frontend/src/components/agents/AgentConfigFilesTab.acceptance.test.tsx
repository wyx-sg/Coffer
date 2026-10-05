// frontend/src/components/agents/AgentConfigFilesTab.acceptance.test.tsx
// Acceptance scenarios for the Config files tab of spec agent-registry "Open
// config files in an external editor or reveal them": the daemon-backed open /
// reveal pair on a file's row, Reveal alone (and no preview) on a file not
// created yet, no edit, new-file, delete or copy-path anywhere; and the
// read-only preview a file's name opens.
import { afterEach, describe, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentConfigFilesTab } from "./AgentConfigFilesTab";
import { agentsApi, type AgentOut, type ConfigFileInfo } from "@/lib/api/agents";
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

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Config files tab — acceptance", () => {
  acceptance("agent-registry", "open a config file and reveal it through the daemon", async () => {
    vi.mocked(agentsApi.listConfigFiles).mockResolvedValue({ items: [INSTRUCTIONS, LOCAL] });
    vi.mocked(fsApi.open).mockResolvedValue(undefined);
    vi.mocked(fsApi.reveal).mockResolvedValue(undefined);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AgentConfigFilesTab agent={AGENT} />
      </QueryClientProvider>,
    );

    const existing = within((await screen.findByText("CLAUDE.md")).closest("li") as HTMLElement);
    fireEvent.click(existing.getByRole("button", { name: "Open in editor" }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(INSTRUCTIONS.path, undefined));
    fireEvent.click(existing.getByRole("button", { name: "Reveal in Finder" }));
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(INSTRUCTIONS.path));

    // The file not created yet: Reveal on its folder only, opening creates nothing.
    const missing = within(screen.getByText("settings.local.json").closest("li") as HTMLElement);
    expect(missing.getByText("Not created")).toBeInTheDocument();
    expect(missing.queryByRole("button", { name: "Open in editor" })).toBeNull();
    fireEvent.click(missing.getByRole("button", { name: "Reveal in Finder" }));
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(LOCAL.folder_path));
    expect(fsApi.open).toHaveBeenCalledTimes(1);

    // Nothing shows content or offers a change, and there is no copy-path fallback.
    for (const name of [/^edit$/i, /save/i, /revert/i, /new file/i, /delete/i, /copy/i]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("textbox")).toBeNull();
    // A file not created yet has no preview; an existing one's name is the way in.
    expect(
      within(missing.getByText("settings.local.json").closest("li") as HTMLElement).queryByRole(
        "button",
        { name: "settings.local.json" },
      ),
    ).toBeNull();
    expect(existing.getByRole("button", { name: "CLAUDE.md" })).toBeInTheDocument();
    expect(agentsApi.configFileContent).not.toHaveBeenCalled();
  });

  acceptance("agent-registry", "preview a config file from its row", async () => {
    vi.mocked(agentsApi.listConfigFiles).mockResolvedValue({ items: [SETTINGS] });
    vi.mocked(agentsApi.configFileContent).mockResolvedValue({
      key: "settings",
      abs_path: SETTINGS.path,
      format: "json",
      content: '{\n  "theme": "dark",\n  "model": "opus"\n}\n',
      size: 70,
      truncated: false,
      binary: false,
    });
    vi.mocked(fsApi.open).mockResolvedValue(undefined);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AgentConfigFilesTab agent={AGENT} />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "settings.json" }));
    const dialog = within(await screen.findByRole("dialog"));
    await waitFor(() => expect(dialog.getByText(/"model"/)).toBeInTheDocument());
    expect(agentsApi.configFileContent).toHaveBeenCalledWith("u-cc", "settings", undefined);
    expect(dialog.getByText(/"theme"/)).toBeInTheDocument();

    // Open in editor (and Reveal) are on the dialog; nothing edits or saves.
    fireEvent.click(dialog.getByRole("button", { name: "Open in editor" }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(SETTINGS.path, undefined));
    expect(dialog.getByRole("button", { name: "Reveal in Finder" })).toBeInTheDocument();
    for (const name of [/^edit$/i, /save/i, /revert/i]) {
      expect(dialog.queryByRole("button", { name })).toBeNull();
    }
    fireEvent.click(dialog.getAllByRole("button", { name: "Close" })[0]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
