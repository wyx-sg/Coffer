// frontend/src/pages/MemoryPage.test.tsx — the Memory page in each state it renders.
//
// Spec memory "Show and edit memory on the Memory page" and "Tidy memory as
// one change": the folder in the header, Tidy handing the prompt to an agent,
// the projects beside the open project's topic files, a file opening in the
// drawer with what breaks the format, Edit quoting the digest it read, Delete
// behind a confirmation, History in place of the panes, and Set up periodic
// tidy… only while scheduled tasks are on. The request helpers
// (`@/lib/api/memory`) are mocked; the query hooks and the cache are real.
import type { ReactNode } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { MemoryFile, MemoryState, MemoryTopic } from "@/lib/api/memoryTypes";
import { acceptance } from "@/test/acceptance";

import { MemoryPage } from "./MemoryPage";

vi.mock("@/lib/api/memory", () => ({
  getMemoryState: vi.fn(),
  listTopics: vi.fn(),
  getMemoryFile: vi.fn(),
  saveMemoryFile: vi.fn(),
  deleteMemoryFile: vi.fn(),
}));
const api = await import("@/lib/api/memory");

let scheduling = true;
vi.mock("@/lib/hooks/useFeatures", () => ({ useFeatureEnabled: () => scheduling }));
vi.mock("@/components/handoff/AgentHandoff", () => ({
  AgentHandoff: ({ prompt, label }: { prompt: string; label: string }) => (
    <button type="button" data-prompt={prompt}>
      {label}
    </button>
  ),
}));
vi.mock("@/components/history/VaultHistoryView", () => ({
  VaultHistoryView: ({ path }: { path: string }) => <div data-testid="history">{path}</div>,
}));
vi.mock("@/components/scheduled-tasks/TaskDialog", () => ({
  TaskDialog: ({ open, draft }: { open: boolean; draft?: { name: string; prompt: string } }) =>
    open ? <div data-testid="task-dialog">{`${draft?.name}|${draft?.prompt}`}</div> : null,
}));

const FOLDER = "github.com-me-app";

function state(over: Partial<MemoryState> = {}): MemoryState {
  return {
    folder_path: "~/.coffer/vault/memory/projects",
    projects: [
      { folder: FOLDER, topics: 2, problems: 1, updated: "2026-11-19" },
      { folder: "scratch", topics: 1, problems: 0, updated: "2026-10-01" },
    ],
    tidy_running: false,
    tidy_started_at: null,
    tidy_handoff: { prompt: "Tidy the developer's memory" },
    ...over,
  };
}

function topic(over: Partial<MemoryTopic>): MemoryTopic {
  return {
    project: FOLDER,
    name: "testing.md",
    title: "Testing",
    type: "feedback",
    updated: "2026-11-19",
    body: "Run only the failing tests.\nNever mock the vault.",
    problems: [],
    ...over,
  };
}

const TOPICS = [
  topic({}),
  topic({
    name: "notes.md",
    title: "notes",
    type: "",
    updated: "",
    problems: ["no_title", "bad_type"],
  }),
];

function file(t: MemoryTopic): MemoryFile {
  return {
    ...t,
    path: `/h/.coffer/vault/memory/projects/${t.project}/${t.name}`,
    text: `---\ntitle: ${t.title}\n---\n${t.body}\n`,
    digest: `d-${t.name}`,
  };
}

function Where() {
  const { pathname, search } = useLocation();
  return <span data-testid="where">{pathname + search}</span>;
}

function renderPage(at = "/memory") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[at]}>
            <Routes>
              <Route
                path="/memory"
                element={
                  <>
                    <MemoryPage />
                    <Where />
                  </>
                }
              />
              <Route path="*" element={<Where />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

// The list renders before its topics load, so a row is waited for, never read at once.
const rowOf = (scope: HTMLElement, text: string) =>
  waitFor(() => {
    const row = within(scope)
      .queryAllByRole("row")
      .find((r) => r.textContent?.includes(text));
    expect(row).toBeDefined();
    return row as HTMLElement;
  });

beforeEach(() => {
  vi.clearAllMocks();
  scheduling = true;
  vi.mocked(api.getMemoryState).mockResolvedValue(state());
  vi.mocked(api.listTopics).mockResolvedValue(TOPICS);
  vi.mocked(api.getMemoryFile).mockImplementation(async (_p, name) =>
    file(TOPICS.find((t) => t.name === name) ?? TOPICS[0]),
  );
});

describe("MemoryPage", () => {
  acceptance("memory", "the Memory page lists projects and their topics", async () => {
    renderPage();
    expect(await screen.findByText("Kept in ~/.coffer/vault/memory/projects")).toBeInTheDocument();
    // The most recently updated project opens; the list says which files break the format.
    const list = await screen.findByTestId("memory-list");
    expect(list).toHaveTextContent(FOLDER);
    expect(list).toHaveTextContent("2 files");
    expect(await rowOf(list, "Testing")).toHaveTextContent("How to work");
    expect(await rowOf(list, "Testing")).toHaveTextContent("Run only the failing tests.");
    expect(
      within(await rowOf(list, "notes")).getByLabelText("Doesn't follow the memory format"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /scratch/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tidy" })).toHaveAttribute(
      "data-prompt",
      "Tidy the developer's memory",
    );
  });

  test("a file opens in the drawer with what breaks the format", async () => {
    renderPage(`/memory?scope=${FOLDER}&file=notes.md`);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("No title");
    expect(dialog).toHaveTextContent("The type is not user, feedback or project");
    expect(dialog).toHaveTextContent("The next tidy fixes it, or edit it yourself.");
  });

  acceptance("memory", "an edit from the Memory page is saved as one change", async () => {
    vi.mocked(api.saveMemoryFile).mockImplementation(async (_p, _n, text) => ({
      ...file(TOPICS[0]),
      text,
    }));
    renderPage(`/memory?scope=${FOLDER}&file=testing.md`);
    const edit = await screen.findByRole("button", { name: "Edit" });
    await waitFor(() => expect(edit).toBeEnabled());
    fireEvent.click(edit);
    const area = await screen.findByLabelText("testing.md");
    fireEvent.change(area, { target: { value: "---\ntitle: Testing\n---\nNew line.\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.saveMemoryFile).toHaveBeenCalledWith(
        FOLDER,
        "testing.md",
        "---\ntitle: Testing\n---\nNew line.\n",
        "d-testing.md",
      ),
    );
  });

  test("delete asks first and quotes the digest it read", async () => {
    vi.mocked(api.deleteMemoryFile).mockResolvedValue(undefined);
    renderPage(`/memory?scope=${FOLDER}&file=testing.md`);
    const del = await screen.findByRole("button", { name: "Delete" });
    await waitFor(() => expect(del).toBeEnabled());
    fireEvent.click(del);
    const dialogs = await screen.findAllByRole("dialog");
    const confirm = dialogs[dialogs.length - 1];
    expect(confirm).toHaveTextContent("Delete testing.md?");
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.deleteMemoryFile).toHaveBeenCalledWith(FOLDER, "testing.md", "d-testing.md"),
    );
  });

  acceptance("memory", "History shows every change to memory", async () => {
    renderPage(`/memory?history=1`);
    expect(await screen.findByTestId("history")).toHaveTextContent("memory/");
    expect(screen.queryByTestId("memory-list")).not.toBeInTheDocument();
  });

  acceptance("memory", "periodic tidy is a scheduled task the person sets up", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "More memory actions" }));
    fireEvent.click(await screen.findByText("Set up periodic tidy…"));
    expect(await screen.findByTestId("task-dialog")).toHaveTextContent(
      "Tidy memory|Tidy the developer's memory",
    );
  });

  test("without scheduled tasks there is no periodic tidy", async () => {
    scheduling = false;
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "More memory actions" }));
    expect(await screen.findByText("History")).toBeInTheDocument();
    expect(screen.queryByText("Set up periodic tidy…")).not.toBeInTheDocument();
  });

  test("an open tidy is said under the header; no memories is an empty state", async () => {
    vi.mocked(api.getMemoryState).mockResolvedValue(state({ tidy_running: true, projects: [] }));
    renderPage();
    expect(await screen.findByRole("status")).toHaveTextContent("An agent is tidying memory.");
    expect(screen.getByText("No memories yet")).toBeInTheDocument();
  });
});
