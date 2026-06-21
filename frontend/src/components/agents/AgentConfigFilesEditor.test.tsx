// frontend/src/components/agents/AgentConfigFilesEditor.test.tsx
// The config viewer is READ-ONLY: a selected file opens in a read-only preview
// (no editable textarea, no Save, no find/replace) with a FileActions bar that
// takes the file to the user's own editor. Directory-backed config keys expand
// into child files that open read-only, and a Coffer memory-projection block
// renders an info annotation. There is no in-app create/delete/save flow.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AgentConfigFilesEditor } from "./AgentConfigFilesEditor";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentConfigFiles: vi.fn(),
  useAgentConfigFile: vi.fn(),
  useAgentConfigChild: vi.fn(),
}));
const { useAgentConfigFiles, useAgentConfigFile, useAgentConfigChild } =
  await import("@/lib/hooks/useAgents");
const filesMock = vi.mocked(useAgentConfigFiles);
const fileMock = vi.mocked(useAgentConfigFile);
const childMock = vi.mocked(useAgentConfigChild);

const FILES = [
  {
    key: "settings",
    display_name: "User settings",
    path: "/home/u/.claude/settings.json",
    folder_path: "/home/u/.claude",
    format: "json" as const,
    exists: true,
    size: 17,
    modified_at: "2026-05-22T00:00:00Z",
  },
];

// A directory-backed config key (kind: "directory") whose children come from
// the list response's `files`.
const DIR = {
  key: "memories",
  display_name: "Memory directory",
  path: "/home/u/.claude/memories",
  folder_path: "/home/u/.claude",
  format: "markdown" as const,
  exists: true,
  size: null,
  modified_at: null,
  kind: "directory" as const,
  files: [
    { relpath: "alpha.md", size: 10, modified_at: "2026-06-01T00:00:00Z" },
    { relpath: "notes/beta.md", size: 5, modified_at: "2026-06-02T00:00:00Z" },
  ],
};

afterEach(() => vi.clearAllMocks());

function stubFile(content: string, extra: Record<string, unknown> = {}) {
  fileMock.mockReturnValue({
    data: {
      key: "settings",
      format: "json",
      exists: true,
      content,
      path: "/home/u/.claude/settings.json",
      folder_path: "/home/u/.claude",
      ...extra,
    },
    isPending: false,
  } as unknown as ReturnType<typeof useAgentConfigFile>);
}

function stubChild(data: Record<string, unknown> | undefined) {
  childMock.mockReturnValue({
    data,
    isPending: false,
  } as unknown as ReturnType<typeof useAgentConfigChild>);
}

function stubDirFiles() {
  filesMock.mockReturnValue({
    data: [...FILES, DIR],
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useAgentConfigFiles>);
}

function stubFiles() {
  filesMock.mockReturnValue({
    data: FILES,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useAgentConfigFiles>);
}

function openSettings() {
  fireEvent.click(screen.getByText("User settings"));
}

describe("AgentConfigFilesEditor (read-only)", () => {
  test("opens a file as a read-only preview (no textarea, Save, or find/replace)", () => {
    stubFiles();
    stubFile('{"theme": "dark"}');
    stubChild(undefined);

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    // Content is shown in a read-only CodeMirror editor, never an editable field.
    const content = document.querySelector(".cm-content");
    expect(content?.textContent).toContain('{"theme": "dark"}');
    expect(content?.getAttribute("contenteditable")).toBe("false");
    expect(document.querySelector("textarea")).toBeNull();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /find ?\/ ?replace/i })).not.toBeInTheDocument();
  });

  test("renders the FileActions bar for the selected file (open/reveal on the web)", () => {
    stubFiles();
    stubFile('{"theme": "dark"}');
    stubChild(undefined);

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    // FileActions offers real open/reveal on both surfaces (daemon-backed on web):
    // open-in-editor + reveal for the file.
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  });

  test("hides not-yet-created allowlisted files from the read-only viewer", () => {
    filesMock.mockReturnValue({
      data: [
        ...FILES,
        {
          key: "memory",
          display_name: "User memory (CLAUDE.md)",
          path: "/home/u/.claude/CLAUDE.md",
          folder_path: "/home/u/.claude",
          format: "markdown" as const,
          exists: false,
          size: null,
          modified_at: null,
        },
      ],
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useAgentConfigFiles>);
    stubChild(undefined);

    render(<AgentConfigFilesEditor name="cc" />);

    // exists=false → not surfaced in the viewer at all (the list API still
    // returns it for the REST/CLI write path; the UI just doesn't show it).
    expect(screen.queryByText("User memory (CLAUDE.md)")).not.toBeInTheDocument();
    expect(screen.queryByText(/not created/i)).not.toBeInTheDocument();
  });

  test("directory node expands to list its children; the node itself shows the hint", () => {
    stubDirFiles();
    stubFile("{}");
    stubChild(undefined);

    render(<AgentConfigFilesEditor name="cc" />);

    // Children hidden until the directory is expanded.
    expect(screen.queryByText("alpha.md")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Memory directory"));
    expect(screen.getByText("alpha.md")).toBeInTheDocument();
    expect(screen.getByText("notes/beta.md")).toBeInTheDocument();

    // Selecting the directory itself shows the hint, not a preview.
    expect(screen.getByText(/this is a directory/i)).toBeInTheDocument();
  });

  test("selecting a child loads its content read-only with its own FileActions", () => {
    stubDirFiles();
    stubFile("{}");
    stubChild({
      key: "memories",
      format: "markdown",
      exists: true,
      content: "hello child",
      path: "/home/u/.claude/memories/alpha.md",
      folder_path: "/home/u/.claude/memories",
    });

    render(<AgentConfigFilesEditor name="cc" />);
    fireEvent.click(screen.getByText("Memory directory"));
    fireEvent.click(screen.getByText("alpha.md"));

    expect(document.querySelector(".cm-content")?.textContent).toContain("hello child");
    expect(document.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("false");
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  });

  test("memory_block content renders the memory-projection annotation", () => {
    stubFiles();
    stubFile("# CLAUDE.md", { memory_block: true });
    stubChild(undefined);

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    expect(screen.getByText(/memory-projection block/i)).toBeInTheDocument();
  });

  test("en and zh locales carry the same agents.config keys", () => {
    const keysOf = (o: Record<string, unknown>) => Object.keys(o).sort();
    expect(keysOf(en.agents.config)).toEqual(keysOf(zh.agents.config));
  });
});
