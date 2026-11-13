// src/pages/ScheduledTasksPage.test.tsx — the Scheduled tasks page: the owner's tasks beside the open one, and New task.
//
// Real QueryClientProvider; only the api modules are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { ScheduledRun, ScheduledTask } from "@/lib/api/scheduledTasks";
import { acceptance } from "@/test/acceptance";
import { ScheduledTasksPage } from "./ScheduledTasksPage";

vi.mock("@/lib/api/scheduledTasks", () => ({
  scheduledTasksApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    runs: vi.fn(),
    runNow: vi.fn(),
    setPrompt: vi.fn(),
  },
}));
vi.mock("@/lib/api/agentModels", () => ({
  agentModelsApi: {
    list: vi.fn().mockResolvedValue({
      models: [{ id: "claude-sonnet", label: "Sonnet", description: "" }],
      default_model: null,
      builtin_default: null,
      resolved_default: null,
    }),
  },
}));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { update: vi.fn(), enable: vi.fn(), disable: vi.fn(), remove: vi.fn() },
}));
const { scheduledTasksApi } = await import("@/lib/api/scheduledTasks");
const api = vi.mocked(scheduledTasksApi);
const { resourcesApi } = await import("@/lib/api/resources");

function task(over: Partial<ScheduledTask> & { uid: string; name: string }): ScheduledTask {
  return {
    description: null,
    enabled: true,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
    last_run: null,
    next_run: "2026-10-30T09:00:00Z",
    running: false,
    prompt: "Summarise the open pull requests\n",
    folder: `/Users/me/.coffer/content/workspace/scheduled-tasks/${over.uid}`,
    config: {
      schedule: { kind: "daily", time: "09:00" },
      agent: "claude_code",
    },
    ...over,
  };
}

const MORNING = task({ uid: "t-1", name: "Morning summary" });
const NIGHTLY = task({
  uid: "t-2",
  name: "Nightly build",
  next_run: "2026-10-29T16:00:00Z",
  prompt: "Check the nightly build\n",
  config: {
    schedule: { kind: "cron", expr: "0 2 * * *" },
    agent: "codex",
    model: "gpt-5",
  },
});

function Where() {
  const { pathname } = useLocation();
  return <div data-testid="where">{pathname}</div>;
}

function renderPage(path = "/scheduled-tasks") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/scheduled-tasks" element={<ScheduledTasksPage />} />
            <Route path="/scheduled-tasks/:uid" element={<ScheduledTasksPage />} />
            <Route path="/scheduled-tasks/:uid/:tab" element={<ScheduledTasksPage />} />
          </Routes>
          <Where />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function rows(): string[] {
  return within(screen.getByRole("list", { name: "Scheduled tasks" }))
    .getAllByRole("listitem")
    .map((li) => li.querySelector(".text-sm")?.textContent ?? "");
}

beforeEach(() => {
  api.list.mockResolvedValue([MORNING, NIGHTLY]);
  api.runs.mockResolvedValue([]);
});
afterEach(() => vi.clearAllMocks());

describe("ScheduledTasksPage", () => {
  test("lists every task in one list, the first open", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Morning summary" })).toBeInTheDocument();
    expect(rows()).toEqual(["Morning summary", "Nightly build"]);
    expect(screen.getAllByText(/Every day at 09:00 · next/).length).toBeGreaterThan(0);
  });

  test("an open task names its agent, model and folder", async () => {
    renderPage("/scheduled-tasks/t-2");
    expect(await screen.findByRole("heading", { name: "Nightly build" })).toBeInTheDocument();
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
    expect(screen.getByText(NIGHTLY.folder)).toBeInTheDocument();
    expect(screen.getByText("the task’s own folder")).toBeInTheDocument();
  });

  test("an open task that names a folder shows it", async () => {
    api.list.mockResolvedValue([
      task({
        uid: "t-3",
        name: "Repo check",
        config: { ...MORNING.config, cwd: "/Users/me/code/app" },
      }),
    ]);
    renderPage("/scheduled-tasks/t-3");
    expect(await screen.findByText("/Users/me/code/app")).toBeInTheDocument();
    expect(screen.queryByText("the task’s own folder")).toBeNull();
  });

  test("a task has two tabs, and an old Files address lands on its Overview", async () => {
    renderPage("/scheduled-tasks/t-1/files");
    expect(await screen.findByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Overview",
      "History",
    ]);
  });

  test("the history says when it shows only the latest runs", async () => {
    const run = {
      task_uid: "t-1",
      task_name: "Morning summary",
      due_at: "2026-10-29T09:00:00Z",
      started_at: "2026-10-29T09:00:00Z",
      finished_at: "2026-10-29T09:02:00Z",
      outcome: "done" as const,
      reason: "",
      catch_up: false,
      trigger: "schedule" as const,
      conversation_id: "",
      conversation: null,
    };
    api.runs.mockResolvedValue(
      Array.from({ length: 200 }, (_, i) => ({ ...run, run_id: `r-${i}` })),
    );
    renderPage("/scheduled-tasks/t-1/runs");
    expect(await screen.findByText("Showing the latest 200 runs.")).toBeInTheDocument();
  });

  test("Run now starts the open task", async () => {
    api.runNow.mockResolvedValue({} as never);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Run now" }));
    await waitFor(() => expect(api.runNow).toHaveBeenCalledWith("t-1"));
  });

  test("Pause switches the task off", async () => {
    vi.mocked(resourcesApi.disable).mockResolvedValue();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Pause" }));
    await waitFor(() => expect(resourcesApi.disable).toHaveBeenCalledWith("t-1"));
  });

  acceptance("scheduled-tasks", "a run's conversation opens from its history", async () => {
    const run = (id: string, over: Partial<ScheduledRun>): ScheduledRun => ({
      run_id: id,
      task_uid: "t-1",
      task_name: "Morning summary",
      due_at: "2026-10-29T09:00:00Z",
      started_at: "2026-10-29T09:00:00Z",
      finished_at: "2026-10-29T09:02:00Z",
      outcome: "done",
      reason: "",
      catch_up: false,
      trigger: "schedule",
      conversation_id: "",
      conversation: null,
      ...over,
    });
    api.runs.mockResolvedValue([
      run("r-2", {
        conversation_id: "c-2",
        conversation: {
          conversation_id: "c-2",
          title: "Open pull requests",
          agent_key: "claude_code",
          session_id: "s-2",
          cwd: "/work",
          running: false,
        },
      }),
      run("r-1", { conversation_id: "c-1" }),
    ]);
    renderPage("/scheduled-tasks/t-1/runs");
    const link = await screen.findByRole("link", { name: "Open pull requests" });
    expect(link).toHaveAttribute("href", "/conversations?open=c-2");
    expect(screen.getByText("Its conversation has been removed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Open in/ })).toBeNull();
  });

  acceptance(
    "scheduled-tasks",
    "the owner reads and edits a task's prompt on its page",
    async () => {
      renderPage("/scheduled-tasks/t-1");
      expect(await screen.findByText("Summarise the open pull requests")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Edit prompt" }));
      expect(await screen.findByRole("textbox", { name: "PROMPT.md" })).toBeInTheDocument();
      // Nothing to save until the text changes.
      expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    },
  );

  acceptance("scheduled-tasks", "the page creates a task", async () => {
    api.list.mockResolvedValue([]);
    api.create.mockResolvedValue(task({ uid: "t-new", name: "Nightly build" }));
    renderPage();
    expect(await screen.findByText("No scheduled tasks yet")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "New task" })[0]);
    const dialog = await screen.findByRole("dialog");
    const create = within(dialog).getByRole("button", { name: "Create task" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Nightly build" } });
    // A task is given its prompt when it is created.
    expect(create).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Prompt/), {
      target: { value: "Check the nightly build" },
    });
    // The folder is optional: left empty, runs work in the task's own.
    expect(within(dialog).getByPlaceholderText("The task's own folder")).toBeInTheDocument();
    const model = within(dialog).getByRole("combobox", { name: "Model" });
    await waitFor(() => {
      fireEvent.keyDown(model, { key: "ArrowDown" });
      expect(screen.getByRole("option", { name: "Sonnet" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("option", { name: "Sonnet" }));
    fireEvent.click(create);
    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    expect(api.create.mock.calls[0][0]).toEqual({
      name: "Nightly build",
      prompt: "Check the nightly build",
      config: {
        schedule: { kind: "daily", time: "09:00" },
        agent: "claude_code",
        model: "claude-sonnet",
        cwd: null,
        catch_up: true,
      },
    });
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent("/scheduled-tasks/t-new"),
    );
  });
});
