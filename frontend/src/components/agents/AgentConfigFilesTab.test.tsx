// frontend/src/components/agents/AgentConfigFilesTab.test.tsx
// The Config files tab: every allowlisted file in one tree grouped by where it
// lives (instructions beside settings, a not-created file marked so), the
// selected file in the URL, a read-only preview behind an explicit Edit, JSON
// checked while typing, a stale save that keeps the draft, a missing file that
// can be created, a directory entry that lists its files, and the unsaved-draft
// guard (the shell's, registered by the draft).
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { AgentConfigFilesTab } from "./AgentConfigFilesTab";
import { UnsavedGuardProvider } from "@/components/shell/UnsavedGuard";
import { agentsApi, type AgentOut, type ConfigFileInfo } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import "@/i18n";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentConfigFiles: vi.fn(),
  useAgentConfigFile: vi.fn(),
  useAgentConfigChild: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useAgents");

const AGENT = {
  uid: "agt_cc",
  type: "claude_code",
  name: "claude_code",
  display_name: "Claude Code",
  config_dir: "/home/u/.claude",
  state: "installed_active",
  version: "2.1.281",
  model: null,
  effort: null,
  tier_models: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
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
  }),
  entry({ key: "instructions", path: "/home/u/.claude/CLAUDE.md", format: "markdown" }),
  entry({
    key: "subagents",
    path: "/home/u/.claude/agents",
    format: "markdown",
    kind: "directory",
    size: null,
    files: [
      { relpath: "code-reviewer.md", size: 2048, modified_at: "2026-09-03T00:00:00Z" },
      { relpath: "test-runner.md", size: 1024, modified_at: "2026-08-11T00:00:00Z" },
    ],
  }),
  entry({ key: "global", path: "/home/u/.claude.json", folder_path: "/home/u" }),
];

function stub(opts: { content?: string; exists?: boolean; child?: string } = {}) {
  vi.mocked(hooks.useAgentConfigFiles).mockReturnValue({
    data: FILES,
    isPending: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useAgentConfigFiles>);
  vi.mocked(hooks.useAgentConfigFile).mockImplementation(
    (_uid, key) =>
      ({
        data: key
          ? {
              key,
              format: key === "instructions" ? "markdown" : "json",
              exists: opts.exists ?? true,
              content: opts.exists === false ? "" : (opts.content ?? '{"theme": "dark"}'),
              fingerprint: "fp1",
              path: FILES.find((f) => f.key === key)?.path ?? "",
              folder_path: "/home/u/.claude",
            }
          : undefined,
        isPending: false,
        refetch: vi.fn(async () => ({})),
      }) as unknown as ReturnType<typeof hooks.useAgentConfigFile>,
  );
  vi.mocked(hooks.useAgentConfigChild).mockImplementation(
    (_uid, key, relpath) =>
      ({
        data: relpath
          ? {
              key,
              format: "markdown",
              exists: true,
              content: opts.child ?? "# reviewer",
              fingerprint: "fpc",
              path: `/home/u/.claude/agents/${relpath}`,
              folder_path: "/home/u/.claude/agents",
            }
          : undefined,
        isPending: false,
        refetch: vi.fn(async () => ({})),
      }) as unknown as ReturnType<typeof hooks.useAgentConfigChild>,
  );
}

function Location() {
  return <output data-testid="location">{useLocation().search}</output>;
}

function renderTab(search = "") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <UnsavedGuardProvider>
            <AgentConfigFilesTab agent={AGENT} />
            <Location />
          </UnsavedGuardProvider>
        ),
      },
    ],
    { initialEntries: [`/agents/claude_code/config${search}`] },
  );
  const ui: ReactNode = (
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
  return render(ui);
}

const fileParam = () =>
  new URLSearchParams(screen.getByTestId("location").textContent ?? "").get("file");

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AgentConfigFilesTab", () => {
  // Config files lists the instructions file beside the settings files.
  acceptance("agent-registry", "the agent detail page carries nine tabs", () => {
    stub();
    renderTab();
    expect(screen.getByText("settings.json")).toBeInTheDocument();
    expect(screen.getByText("CLAUDE.md")).toBeInTheDocument();
    expect(screen.getByText("Instructions")).toBeInTheDocument();
    expect(screen.getByText("agents/")).toBeInTheDocument();
    // Directories start open.
    expect(screen.getByText("code-reviewer.md")).toBeInTheDocument();
    // Not hidden: shown and marked.
    const local = screen.getByText("settings.local.json").closest("button") as HTMLElement;
    expect(within(local).getByText("not created")).toBeInTheDocument();
    // The file kept beside the config directory is grouped under home.
    expect(screen.getByText("~ (home)")).toBeInTheDocument();
    expect(screen.getByText(".claude.json")).toBeInTheDocument();
    expect(screen.getByText(/select a file to view/i)).toBeInTheDocument();
  });

  test("picking a file keeps it in ?file= and opens it read-only behind Edit", () => {
    stub();
    renderTab();
    fireEvent.click(screen.getByText("settings.json"));
    expect(fileParam()).toBe("settings");
    expect(screen.getByText("Read-only")).toBeInTheDocument();
    expect(document.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("false");
    expect(document.querySelector("textarea")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(screen.getByRole("textbox")).toHaveValue('{"theme": "dark"}');
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    expect(screen.getByText("/home/u/.claude/settings.json")).toBeInTheDocument();
  });

  test("?file= opens that file on load", () => {
    stub();
    renderTab("?file=instructions");
    expect(screen.getByText(/instructions claude code reads at the start/i)).toBeInTheDocument();
  });

  test("an invalid JSON draft names the line and holds Save back", () => {
    stub();
    renderTab("?file=settings");
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: '{\n  "a": 1\n  "b": 2\n}' },
    });
    expect(screen.getByText("Unsaved change")).toBeInTheDocument();
    expect(screen.getByText(/line 3, column \d+: not valid json/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: '{"a": 2}' } });
    expect(screen.getByText("Valid JSON")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeEnabled();
  });

  test("a save refused as stale keeps the draft and offers copy and reload", async () => {
    stub();
    vi.spyOn(agentsApi, "writeConfigFile").mockRejectedValue(
      new ApiError("CONFIG_FILE_STALE", "changed on disk"),
    );
    renderTab("?file=settings");
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: '{"theme": "light"}' } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(
      await screen.findByText(/save refused — settings.json changed on disk/i),
    ).toBeInTheDocument();
    expect(vi.mocked(agentsApi.writeConfigFile)).toHaveBeenCalledWith("agt_cc", "settings", {
      content: '{"theme": "light"}',
      expected_fingerprint: "fp1",
    });
    expect(screen.getByRole("textbox")).toHaveValue('{"theme": "light"}');
    expect(screen.getByRole("button", { name: /copy my edits/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /discard my edits and reload/i }),
    ).toBeInTheDocument();
  });

  test("a file not created yet offers to create it; saving writes it", async () => {
    stub({ exists: false });
    const write = vi.spyOn(agentsApi, "writeConfigFile").mockResolvedValue(FILES[1]);
    renderTab("?file=settings_local");
    expect(screen.getByText(/this file doesn’t exist yet/i)).toBeInTheDocument();
    expect(screen.getByText("Read-only until created")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /create settings.local.json/i }));
    expect(screen.getByRole("textbox")).toHaveValue("{}\n");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(write).toHaveBeenCalledWith("agt_cc", "settings_local", {
        content: "{}\n",
        expected_fingerprint: "fp1",
      }),
    );
  });

  test("a directory entry lists its files; picking one opens it", () => {
    stub();
    renderTab("?file=subagents");
    expect(screen.getByText("Directory · 2 files")).toBeInTheDocument();
    const list = screen.getByText(/custom subagent definitions/i).closest("div")?.parentElement
      ?.parentElement as HTMLElement;
    fireEvent.click(within(list).getAllByText("test-runner.md")[0]);
    expect(fileParam()).toBe("subagents/test-runner.md");
    expect(document.querySelector(".cm-content")?.textContent).toContain("# reviewer");
  });

  test("a directory entry creates a file from a template and deletes one after asking", async () => {
    stub();
    const write = vi.spyOn(agentsApi, "writeConfigChild").mockResolvedValue(FILES[1]);
    const del = vi.spyOn(agentsApi, "deleteConfigChild").mockResolvedValue(undefined);
    renderTab("?file=subagents");

    fireEvent.click(screen.getByRole("button", { name: "Delete test-runner.md" }));
    const confirm = await screen.findByRole("dialog");
    expect(confirm).toHaveTextContent("Delete test-runner.md?");
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("agt_cc", "subagents", "test-runner.md"));
    fireEvent.click(screen.getByRole("button", { name: "New file" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("New file in agents/");
    const create = within(dialog).getByRole("button", { name: "Create" });
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "bad/name" } });
    expect(create).toBeDisabled();
    fireEvent.change(within(dialog).getByRole("textbox"), {
      target: { value: "release-checker.md" },
    });
    fireEvent.click(create);
    await waitFor(() =>
      expect(write).toHaveBeenCalledWith("agt_cc", "subagents", "release-checker.md", {
        content: "---\nname: release-checker\ndescription: \n---\n\n",
      }),
    );
  });

  test("switching files with a dirty draft asks first; keep editing stays", async () => {
    stub();
    renderTab("?file=settings");
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: '{"theme": "light"}' } });

    fireEvent.click(screen.getByText("CLAUDE.md"));
    const dialog = await screen.findByRole("dialog", { name: "Leave without saving?" });
    expect(dialog).toHaveTextContent("You edited settings.json in Claude Code.");
    expect(fileParam()).toBe("settings");
    fireEvent.click(within(dialog).getByRole("button", { name: /keep editing/i }));
    expect(screen.getByRole("textbox")).toHaveValue('{"theme": "light"}');
  });

  test("discarding at the guard opens the file picked", async () => {
    stub();
    renderTab("?file=settings");
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "changed" } });
    fireEvent.click(screen.getByText("CLAUDE.md"));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: /discard changes/i }),
    );
    await waitFor(() => expect(fileParam()).toBe("instructions"));
    expect(document.querySelector("textarea")).toBeNull();
  });

  test("a dirty draft blocks page unload; a clean one does not", () => {
    stub();
    const fire = () => {
      const e = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(e);
      return e.defaultPrevented;
    };
    renderTab("?file=settings");
    expect(fire()).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "{ }" } });
    expect(fire()).toBe(true);
  });
});
