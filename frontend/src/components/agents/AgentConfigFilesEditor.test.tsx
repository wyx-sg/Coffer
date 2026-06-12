// frontend/src/components/agents/AgentConfigFilesEditor.test.tsx
// The config viewer is editable: a selected file opens in an editable textarea
// with a Save control, surfaces a save error, and offers a dependency-free
// find/replace bar that operates on the editable content. Directory-backed
// config keys expand into child files (create/delete), saves carry the
// content query's expected_fingerprint, a 409 CONFIG_FILE_STALE save shows a
// reload banner, and a memory-projection block renders an info notice.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ApiError } from "@/lib/api/errors";
import { AgentConfigFilesEditor } from "./AgentConfigFilesEditor";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentConfigFiles: vi.fn(),
  useAgentConfigFile: vi.fn(),
  useSaveAgentConfigFile: vi.fn(),
  useAgentConfigChild: vi.fn(),
  useWriteConfigChild: vi.fn(),
  useDeleteConfigChild: vi.fn(),
}));
const {
  useAgentConfigFiles,
  useAgentConfigFile,
  useSaveAgentConfigFile,
  useAgentConfigChild,
  useWriteConfigChild,
  useDeleteConfigChild,
} = await import("@/lib/hooks/useAgents");
const filesMock = vi.mocked(useAgentConfigFiles);
const fileMock = vi.mocked(useAgentConfigFile);
const saveMock = vi.mocked(useSaveAgentConfigFile);
const childMock = vi.mocked(useAgentConfigChild);
const writeChildMock = vi.mocked(useWriteConfigChild);
const deleteChildMock = vi.mocked(useDeleteConfigChild);

const FILES = [
  {
    key: "settings",
    display_name: "User settings",
    path: "/home/u/.claude/settings.json",
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

// Baseline stubs for the directory-child hooks so every render works; tests
// that exercise children re-stub with their own data/spies.
beforeEach(() => {
  stubChild(undefined);
  stubWriteChild();
  stubDeleteChild();
});

function stubFile(content: string, extra: Record<string, unknown> = {}) {
  const refetch = vi.fn();
  fileMock.mockReturnValue({
    data: { key: "settings", format: "json", exists: true, content, ...extra },
    isPending: false,
    refetch,
  } as unknown as ReturnType<typeof useAgentConfigFile>);
  return refetch;
}

function stubChild(data: Record<string, unknown> | undefined) {
  const refetch = vi.fn();
  childMock.mockReturnValue({
    data,
    isPending: false,
    refetch,
  } as unknown as ReturnType<typeof useAgentConfigChild>);
  return refetch;
}

function stubWriteChild(overrides: Partial<{ isPending: boolean; error: unknown }> = {}) {
  const mutate = vi.fn();
  writeChildMock.mockReturnValue({
    mutate,
    reset: vi.fn(),
    isPending: overrides.isPending ?? false,
    error: overrides.error ?? null,
  } as unknown as ReturnType<typeof useWriteConfigChild>);
  return mutate;
}

function stubDeleteChild() {
  const mutate = vi.fn();
  deleteChildMock.mockReturnValue({
    mutate,
    reset: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useDeleteConfigChild>);
  return mutate;
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

function stubSave(
  overrides: Partial<{ mutate: ReturnType<typeof vi.fn>; isPending: boolean; error: unknown }> = {},
) {
  const mutate = overrides.mutate ?? vi.fn();
  saveMock.mockReturnValue({
    mutate,
    reset: vi.fn(),
    isPending: overrides.isPending ?? false,
    error: overrides.error ?? null,
  } as unknown as ReturnType<typeof useSaveAgentConfigFile>);
  return mutate;
}

function openSettings() {
  fireEvent.click(screen.getByText("User settings"));
}

describe("AgentConfigFilesEditor (editable)", () => {
  test("edits the file and Save calls the mutation", () => {
    stubFiles();
    stubFile('{"theme": "dark"}');
    const mutate = stubSave();

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    const editor = screen.getByRole("textbox", { name: /contents of settings/i });
    expect(editor).toHaveValue('{"theme": "dark"}');
    expect(editor).not.toHaveAttribute("readonly");

    // Save is disabled until the content is dirtied.
    const saveBtn = screen.getByRole("button", { name: /^save$/i });
    expect(saveBtn).toBeDisabled();

    fireEvent.change(editor, { target: { value: '{"theme": "light"}' } });
    expect(saveBtn).toBeEnabled();
    fireEvent.click(saveBtn);

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ key: "settings", content: '{"theme": "light"}' });
  });

  test("renders a save error from a malformed-content rejection", () => {
    stubFiles();
    stubFile("{not json");
    stubSave({ error: new ApiError("CONFIG_FILE_FORMAT_INVALID", "invalid json content") });

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    expect(screen.getByRole("alert")).toHaveTextContent(/format|unchanged/i);
  });

  test("find/replace bar shows match count and Replace all mutates the content", () => {
    stubFiles();
    stubFile("aXbXc");
    stubSave();

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    // Open the find/replace toolbar.
    fireEvent.click(screen.getByRole("button", { name: /find ?\/ ?replace/i }));

    const findInput = screen.getByPlaceholderText(/^find$/i);
    fireEvent.change(findInput, { target: { value: "X" } });
    expect(screen.getByTestId("find-match-count")).toHaveTextContent("2");

    const replaceInput = screen.getByPlaceholderText(/^replace$/i);
    fireEvent.change(replaceInput, { target: { value: "Y" } });
    fireEvent.click(screen.getByRole("button", { name: /replace all/i }));

    const editor = screen.getByRole("textbox", { name: /contents of settings/i });
    expect(editor).toHaveValue("aYbYc");
  });

  test("Find next selects the match and advances on repeat clicks", () => {
    stubFiles();
    stubFile("aXbXc");
    stubSave();

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();
    fireEvent.click(screen.getByRole("button", { name: /find ?\/ ?replace/i }));
    fireEvent.change(screen.getByPlaceholderText(/^find$/i), { target: { value: "X" } });

    const editor = screen.getByRole("textbox", {
      name: /contents of settings/i,
    }) as HTMLTextAreaElement;
    const findNext = screen.getByRole("button", { name: /find next/i });

    // First click selects the first match (so the user jumps to it on screen)…
    fireEvent.click(findNext);
    expect(editor.selectionStart).toBe(1);
    expect(editor.selectionEnd).toBe(2);

    // …and a second click advances to the next occurrence.
    fireEvent.click(findNext);
    expect(editor.selectionStart).toBe(3);
    expect(editor.selectionEnd).toBe(4);
  });

  test("lists not-yet-created allowlisted files and lets you open one (empty)", () => {
    // settings exists; CLAUDE.md (memory) does not exist yet.
    filesMock.mockReturnValue({
      data: [
        ...FILES,
        {
          key: "memory",
          display_name: "User memory (CLAUDE.md)",
          path: "/home/u/.claude/CLAUDE.md",
          format: "markdown" as const,
          exists: false,
          size: null,
          modified_at: null,
        },
      ],
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useAgentConfigFiles>);
    // The not-yet-created file reads back as empty without being created.
    fileMock.mockReturnValue({
      data: { key: "memory", format: "markdown", exists: false, content: "" },
      isPending: false,
    } as unknown as ReturnType<typeof useAgentConfigFile>);
    stubSave();

    render(<AgentConfigFilesEditor name="cc" />);

    // The absent file is listed (Story 7) and flagged as not created.
    const memoryBtn = screen.getByText("User memory (CLAUDE.md)").closest("button")!;
    expect(memoryBtn).toBeInTheDocument();
    expect(screen.getByText(/not created/i)).toBeInTheDocument();

    // Opening it shows an empty editor (the read does not create the file).
    fireEvent.click(memoryBtn);
    expect(screen.getByRole("textbox", { name: /contents of memory/i })).toHaveValue("");
  });

  test("Replace swaps the selected match then advances the selection to the next", () => {
    stubFiles();
    stubFile("aXbXc");
    stubSave();

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();
    fireEvent.click(screen.getByRole("button", { name: /find ?\/ ?replace/i }));
    fireEvent.change(screen.getByPlaceholderText(/^find$/i), { target: { value: "X" } });
    fireEvent.change(screen.getByPlaceholderText(/^replace$/i), { target: { value: "Y" } });

    const editor = screen.getByRole("textbox", {
      name: /contents of settings/i,
    }) as HTMLTextAreaElement;
    const replaceBtn = screen.getByRole("button", { name: /^replace$/i });

    // Nothing selected yet → first click just selects the first match.
    fireEvent.click(replaceBtn);
    expect(editor.selectionStart).toBe(1);

    // Second click replaces it and selects the next match against the NEW text
    // (the deferred selection is applied once the controlled value re-renders).
    fireEvent.click(replaceBtn);
    expect(editor).toHaveValue("aYbXc");
    expect(editor.selectionStart).toBe(3);
    expect(editor.selectionEnd).toBe(4);
  });

  test("directory node expands to list its children; the node itself is not editable", () => {
    stubDirFiles();
    stubFile("{}");
    stubSave();

    render(<AgentConfigFilesEditor name="cc" />);

    // Children hidden until the directory is expanded.
    expect(screen.queryByText("alpha.md")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Memory directory"));
    expect(screen.getByText("alpha.md")).toBeInTheDocument();
    expect(screen.getByText("notes/beta.md")).toBeInTheDocument();

    // Selecting the directory itself shows the hint, not an editor.
    expect(screen.getByText(/this is a directory/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  test("selecting a child loads its content and Save passes the child fingerprint", () => {
    stubDirFiles();
    stubFile("{}");
    stubSave();
    stubChild({
      key: "memories",
      format: "markdown",
      exists: true,
      content: "hello",
      fingerprint: "fp-child-1",
    });
    const writeMutate = stubWriteChild();

    render(<AgentConfigFilesEditor name="cc" />);
    fireEvent.click(screen.getByText("Memory directory"));
    fireEvent.click(screen.getByText("alpha.md"));

    const editor = screen.getByRole("textbox", { name: /contents of alpha\.md/i });
    expect(editor).toHaveValue("hello");

    fireEvent.change(editor, { target: { value: "hello world" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(writeMutate).toHaveBeenCalledTimes(1);
    expect(writeMutate.mock.calls[0][0]).toEqual({
      key: "memories",
      relpath: "alpha.md",
      content: "hello world",
      expected_fingerprint: "fp-child-1",
    });
  });

  test("new-file flow rejects a non-.md name inline, then creates a valid one", async () => {
    stubDirFiles();
    stubFile("{}");
    stubSave();
    const writeMutate = stubWriteChild();

    render(<AgentConfigFilesEditor name="cc" />);
    fireEvent.click(screen.getByRole("button", { name: /new file/i }));

    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox");
    const create = within(dialog).getByRole("button", { name: /new file/i });

    // Client-side validation mirrors the server rules: .md only, no "..",
    // no leading "/".
    for (const bad of ["notes.txt", "../escape.md", "/abs.md"]) {
      fireEvent.change(input, { target: { value: bad } });
      fireEvent.click(create);
      expect(within(dialog).getByRole("alert")).toHaveTextContent(/\.md/);
      expect(writeMutate).not.toHaveBeenCalled();
    }

    fireEvent.change(input, { target: { value: "notes/today.md" } });
    fireEvent.click(create);
    expect(writeMutate).toHaveBeenCalledTimes(1);
    expect(writeMutate.mock.calls[0][0]).toEqual({
      key: "memories",
      relpath: "notes/today.md",
      content: "",
    });
  });

  test("deleting a child flows through the confirm dialog", async () => {
    stubDirFiles();
    stubFile("{}");
    stubSave();
    stubChild({ key: "memories", format: "markdown", exists: true, content: "x" });
    const deleteMutate = stubDeleteChild();

    render(<AgentConfigFilesEditor name="cc" />);
    fireEvent.click(screen.getByText("Memory directory"));
    fireEvent.click(screen.getByText("alpha.md"));

    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(deleteMutate).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    expect(deleteMutate).toHaveBeenCalledTimes(1);
    expect(deleteMutate.mock.calls[0][0]).toEqual({ key: "memories", relpath: "alpha.md" });
  });

  test("file Save passes the content query's expected_fingerprint", () => {
    stubFiles();
    stubFile("{}", { fingerprint: "fp-1" });
    const mutate = stubSave();

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    fireEvent.change(screen.getByRole("textbox", { name: /contents of settings/i }), {
      target: { value: "{ }" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(mutate.mock.calls[0][0]).toEqual({
      key: "settings",
      content: "{ }",
      expected_fingerprint: "fp-1",
    });
  });

  test("409 CONFIG_FILE_STALE shows the reload banner and Reload refetches", () => {
    stubFiles();
    const refetch = stubFile("{}", { fingerprint: "fp-1" });
    const reset = vi.fn();
    saveMock.mockReturnValue({
      mutate: vi.fn(),
      reset,
      isPending: false,
      error: new ApiError("CONFIG_FILE_STALE", "file changed on disk"),
    } as unknown as ReturnType<typeof useSaveAgentConfigFile>);

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    expect(screen.getByRole("alert")).toHaveTextContent(/changed on disk/i);
    reset.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /reload/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(reset).toHaveBeenCalled();
  });

  test("memory_block content renders the memory-projection notice", () => {
    stubFiles();
    stubFile("# CLAUDE.md", { memory_block: true });
    stubSave();

    render(<AgentConfigFilesEditor name="cc" />);
    openSettings();

    expect(screen.getByText(/memory-projection block/i)).toBeInTheDocument();
  });

  test("en and zh locales carry the same agents.config keys", () => {
    const keysOf = (o: Record<string, unknown>) => Object.keys(o).sort();
    expect(keysOf(en.agents.config)).toEqual(keysOf(zh.agents.config));
    expect(keysOf(en.agents.config.find)).toEqual(keysOf(zh.agents.config.find));
  });
});
