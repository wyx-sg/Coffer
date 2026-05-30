// frontend/src/components/agents/AgentConfigFilesEditor.test.tsx
// The config viewer is editable: a selected file opens in an editable textarea
// with a Save control, surfaces a save error, and offers a dependency-free
// find/replace bar that operates on the editable content.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ApiError } from "@/lib/api/errors";
import { AgentConfigFilesEditor } from "./AgentConfigFilesEditor";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentConfigFiles: vi.fn(),
  useAgentConfigFile: vi.fn(),
  useSaveAgentConfigFile: vi.fn(),
}));
const { useAgentConfigFiles, useAgentConfigFile, useSaveAgentConfigFile } = await import(
  "@/lib/hooks/useAgents"
);
const filesMock = vi.mocked(useAgentConfigFiles);
const fileMock = vi.mocked(useAgentConfigFile);
const saveMock = vi.mocked(useSaveAgentConfigFile);

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

afterEach(() => vi.clearAllMocks());

function stubFile(content: string) {
  fileMock.mockReturnValue({
    data: { key: "settings", format: "json", exists: true, content },
    isPending: false,
  } as unknown as ReturnType<typeof useAgentConfigFile>);
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
});
