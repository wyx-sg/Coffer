// frontend/src/components/agents/AgentConfigFilesTab.test.tsx
// The Config files tab: every allowlisted file as one read-only row — name,
// folder, size and modified time, Open in editor and Reveal in Finder — with a
// directory entry's files under it and a not-created file marked. Only the
// network boundary (`agentsApi`, `fsApi`) is mocked.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentConfigFilesTab } from "./AgentConfigFilesTab";
import { agentsApi, type AgentOut, type ConfigFileInfo } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";
import { fsApi } from "@/lib/api/fs";
import { acceptance } from "@/test/acceptance";
import "@/i18n";

vi.mock("@/lib/api/agents", () => ({ agentsApi: { listConfigFiles: vi.fn() } }));
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

function renderTab(items: ConfigFileInfo[] = FILES) {
  vi.mocked(agentsApi.listConfigFiles).mockResolvedValue({ items });
  vi.mocked(fsApi.open).mockResolvedValue(undefined);
  vi.mocked(fsApi.reveal).mockResolvedValue(undefined);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentConfigFilesTab agent={AGENT} />
    </QueryClientProvider>,
  );
}

const rowOf = async (name: string) =>
  within((await screen.findByText(name)).closest("li") as HTMLElement);

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
      expect(await screen.findByText("settings.json")).toBeInTheDocument();
      expect(screen.getByText("Config files · Claude Code")).toBeInTheDocument();
      expect(screen.getByText("CLAUDE.md")).toBeInTheDocument();
      expect(screen.getByText("settings.local.json")).toBeInTheDocument();
      expect(screen.getByText(".claude.json")).toBeInTheDocument();
    },
  );

  test("each row names the file, its folder, size and modified time", async () => {
    renderTab();
    const row = await rowOf("CLAUDE.md");
    expect(row.getByText("~/.claude")).toBeInTheDocument();
    expect(row.getByText(/^2 KB · 2026-09-01 /)).toBeInTheDocument();
    expect(
      row.getByText("Instructions Claude Code reads at the start of every session."),
    ).toBeInTheDocument();
  });

  test("a directory entry lists its files, nested ones by their relative path", async () => {
    renderTab();
    const dir = await rowOf("agents/");
    expect(dir.getByText("Custom subagents, one Markdown file each.")).toBeInTheDocument();
    expect(dir.queryByRole("button", { name: "Open in editor" })).toBeNull();
    const child = await rowOf("code-reviewer.md");
    expect(child.getByText("~/.claude/agents")).toBeInTheDocument();
    expect(child.getByText(/^2 KB · 2026-09-03 /)).toBeInTheDocument();
    fireEvent.click(child.getByRole("button", { name: "Open in editor" }));
    await waitFor(() =>
      expect(fsApi.open).toHaveBeenCalledWith("/home/u/.claude/agents/code-reviewer.md", undefined),
    );
    const nested = await rowOf("team/test-runner.md");
    fireEvent.click(nested.getByRole("button", { name: "Reveal in Finder" }));
    await waitFor(() =>
      expect(fsApi.reveal).toHaveBeenCalledWith("/home/u/.claude/agents/team/test-runner.md"),
    );
  });

  test("an empty or missing directory entry has no rows under it", async () => {
    renderTab([
      entry({ key: "subagents", path: "/home/u/.claude/agents", kind: "directory", files: [] }),
    ]);
    expect(await screen.findByText("No files yet.")).toBeInTheDocument();
  });

  test("the header reveals the agent's config directory", async () => {
    renderTab();
    await screen.findByText("settings.json");
    // The header's icon button comes first, before any row's.
    fireEvent.click(screen.getAllByRole("button", { name: "Reveal in Finder" })[0]);
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith("/home/u/.claude"));
  });

  test("a failed listing says so and offers a retry", async () => {
    vi.mocked(agentsApi.listConfigFiles).mockRejectedValue(new ApiError("INTERNAL", "boom"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AgentConfigFilesTab agent={AGENT} />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
