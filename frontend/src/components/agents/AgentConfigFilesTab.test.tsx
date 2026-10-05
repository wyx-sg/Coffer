// frontend/src/components/agents/AgentConfigFilesTab.test.tsx
// The Config files tab: a tree of every allowlisted file on the left (a
// directory entry's files under it, a not-created file marked and not
// openable) and the selected file read-only on the right, the first existing
// file by default, the selection in `?file=`. Only the network boundary
// (`agentsApi`, `fsApi`) is mocked.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentConfigFilesTab } from "./AgentConfigFilesTab";
import { agentsApi, type AgentOut, type ConfigFileInfo } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";
import { fsApi } from "@/lib/api/fs";
import { acceptance } from "@/test/acceptance";
import "@/i18n";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: { listConfigFiles: vi.fn(), configFileContent: vi.fn() },
}));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));

const AGENT = {
  uid: "agt_cc",
  type: "claude_code",
  name: "claude_code",
  display_name: "Claude Code",
  config_dir: "/home/u/.claude",
} as AgentOut;

const entry = (over: Partial<ConfigFileInfo>): ConfigFileInfo => ({
  key: "settings",
  display_name: "User settings",
  path: "/home/u/.claude/settings.json",
  folder_path: "/home/u/.claude",
  kind: "file",
  format: "json",
  exists: true,
  files: null,
  size: 17,
  modified_at: "2026-09-01T00:00:00Z",
  ...over,
});

const FILES: ConfigFileInfo[] = [
  entry({}),
  entry({
    key: "settings_local",
    path: "/home/u/.claude/settings.local.json",
    exists: false,
    size: null,
    modified_at: null,
  }),
  entry({ key: "instructions", path: "/home/u/.claude/CLAUDE.md", format: "markdown", size: 2048 }),
  entry({
    key: "subagents",
    path: "/home/u/.claude/agents",
    format: "markdown",
    kind: "directory",
    size: null,
    modified_at: null,
    files: [
      {
        relpath: "code-reviewer.md",
        path: "/home/u/.claude/agents/code-reviewer.md",
        size: 2048,
        modified_at: "2026-09-03T00:00:00Z",
      },
      {
        relpath: "team/test-runner.md",
        path: "/home/u/.claude/agents/team/test-runner.md",
        size: 1024,
        modified_at: "2026-08-11T00:00:00Z",
      },
    ],
  }),
  entry({ key: "global", path: "/home/u/.claude.json", folder_path: "/home/u", size: 90 }),
];

const content = (over: Record<string, unknown>) => ({
  key: "settings",
  abs_path: "/home/u/.claude/settings.json",
  format: "json",
  content: '{"theme":"dark"}',
  size: 17,
  truncated: false,
  binary: false,
  ...over,
});

function renderTab(items: ConfigFileInfo[] = FILES, url = "/") {
  vi.mocked(agentsApi.listConfigFiles).mockResolvedValue({ items });
  vi.mocked(agentsApi.configFileContent).mockImplementation(async (_uid, key, child) => {
    if (key === "instructions") {
      return content({ key, abs_path: "/home/u/.claude/CLAUDE.md", content: "Be terse." }) as never;
    }
    if (key === "subagents") {
      return content({
        key,
        abs_path: `/home/u/.claude/agents/${child}`,
        content: `Agent ${child}`,
      }) as never;
    }
    return content({ key }) as never;
  });
  vi.mocked(fsApi.open).mockResolvedValue(undefined);
  vi.mocked(fsApi.reveal).mockResolvedValue(undefined);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <AgentConfigFilesTab agent={AGENT} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const treeItem = (name: string) => screen.findByRole("treeitem", { name: new RegExp(name) });

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("AgentConfigFilesTab", () => {
  // The Config files half of the detail-page scenario: the instructions file is
  // listed beside the settings files.
  acceptance(
    "agent-registry",
    "the agent detail page carries six tabs and a More menu",
    async () => {
      renderTab();
      for (const n of [
        "settings\\.json",
        "CLAUDE\\.md",
        "settings\\.local\\.json",
        "\\.claude\\.json",
      ]) {
        expect(await treeItem(n)).toBeInTheDocument();
      }
      expect(screen.getByText("Config files · Claude Code")).toBeInTheDocument();
    },
  );

  test("the tree lists the directory's files under it and the first existing file is open", async () => {
    renderTab();
    for (const n of ["agents", "code-reviewer\\.md", "team/test-runner\\.md"]) {
      expect(await treeItem(n)).toBeInTheDocument();
    }
    // The first existing file is previewed without a click.
    expect(await screen.findByText(/"theme"/)).toBeInTheDocument();
    expect(agentsApi.configFileContent).toHaveBeenCalledWith("agt_cc", "settings", undefined);
    expect(screen.getByRole("treeitem", { name: /settings\.json/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("selecting a file previews it; a directory child is read by its relpath", async () => {
    renderTab();
    fireEvent.click(await treeItem("CLAUDE\\.md"));
    expect(await screen.findByText("Be terse.")).toBeInTheDocument();
    fireEvent.click(await treeItem("team/test-runner\\.md"));
    expect(await screen.findByText("Agent team/test-runner.md")).toBeInTheDocument();
    expect(agentsApi.configFileContent).toHaveBeenCalledWith(
      "agt_cc",
      "subagents",
      "team/test-runner.md",
    );
  });

  test("the selection comes from the URL", async () => {
    renderTab(FILES, "/?file=subagents/code-reviewer.md");
    expect(await screen.findByText("Agent code-reviewer.md")).toBeInTheDocument();
    expect(agentsApi.configFileContent).not.toHaveBeenCalledWith("agt_cc", "settings", undefined);
  });

  test("a not-created file is marked and cannot be previewed", async () => {
    renderTab();
    const missing = await treeItem("settings\\.local\\.json");
    expect(missing).toHaveTextContent("Not created");
    await screen.findByText(/"theme"/);
    fireEvent.click(missing);
    expect(missing).toHaveAttribute("aria-selected", "false");
    expect(agentsApi.configFileContent).not.toHaveBeenCalledWith(
      "agt_cc",
      "settings_local",
      expect.anything(),
    );
  });

  test("a directory row folds its files", async () => {
    renderTab();
    fireEvent.click(await treeItem("agents"));
    expect(screen.queryByRole("treeitem", { name: /code-reviewer\.md/ })).toBeNull();
  });

  test("the open file's Open in editor goes through the daemon", async () => {
    renderTab();
    await screen.findByText(/"theme"/);
    fireEvent.click(await screen.findByRole("button", { name: "Open in editor" }));
    await waitFor(() =>
      expect(fsApi.open).toHaveBeenCalledWith("/home/u/.claude/settings.json", undefined),
    );
  });

  test("with no existing file there is nothing to preview", async () => {
    renderTab([entry({ exists: false, size: null, modified_at: null })]);
    expect(await screen.findByText("Select a file to view.")).toBeInTheDocument();
    expect(agentsApi.configFileContent).not.toHaveBeenCalled();
  });

  test("the header reveals the agent's config directory", async () => {
    renderTab();
    await treeItem("settings\\.json");
    // The header's icon button comes first, before the viewer's.
    fireEvent.click(screen.getAllByRole("button", { name: "Reveal in Finder" })[0]);
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith("/home/u/.claude"));
  });

  test("a failed listing says so and offers a retry", async () => {
    vi.mocked(agentsApi.listConfigFiles).mockRejectedValue(new ApiError("INTERNAL", "boom"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AgentConfigFilesTab agent={AGENT} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
