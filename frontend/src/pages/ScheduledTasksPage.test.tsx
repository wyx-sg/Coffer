// src/pages/ScheduledTasksPage.test.tsx — the Scheduled tasks page: the owner's tasks beside the open one, New task, and Coffer's own workers.
//
// Real QueryClientProvider; only the api modules are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { DaemonWorker } from "@/lib/api/daemon";
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
    chats: vi.fn(),
    setDailyReport: vi.fn(),
  },
}));
vi.mock("@/lib/api/daemon", () => ({ daemonApi: { status: vi.fn() } }));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { update: vi.fn(), enable: vi.fn(), disable: vi.fn(), remove: vi.fn() },
}));
const { scheduledTasksApi } = await import("@/lib/api/scheduledTasks");
const api = vi.mocked(scheduledTasksApi);
const { daemonApi } = await import("@/lib/api/daemon");
const { resourcesApi } = await import("@/lib/api/resources");

function task(over: Partial<ScheduledTask> & { uid: string; name: string }): ScheduledTask {
  return {
    description: null,
    enabled: true,
    channel_name: "Work",
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
    last_run: null,
    next_run: "2026-10-30T09:00:00Z",
    running: false,
    config: {
      schedule: { kind: "daily", time: "09:00" },
      prompt: "Summarise the open pull requests",
      chat: { channel: "ch-1", chat_id: "owner" },
    },
    ...over,
  };
}

const MORNING = task({ uid: "t-1", name: "Morning summary" });
const FOLLOW_UP = task({
  uid: "t-2",
  name: "Deploy check",
  next_run: "2026-10-29T16:00:00Z",
  config: {
    schedule: { kind: "once", at: "2026-10-29T16:00:00Z" },
    prompt: "Check the deploy reached live",
    chat: { channel: "ch-1", chat_id: "grp", chat_kind: "group", thread_id: "th-1" },
    session: "continue",
    origin: "agent",
    chain_index: 1,
    mention: { user_id: "u-1", name: "Sam" },
  },
});

function worker(name: string, over: Partial<DaemonWorker> = {}): DaemonWorker {
  return {
    name,
    mode: "timer",
    state: "waiting",
    runs: 4,
    failures: 0,
    last_ok: true,
    last_started_at: "2026-10-29T09:55:00Z",
    last_duration_ms: 12,
    next_run_at: null,
    ...over,
  };
}

const WORKERS = [
  worker("sync-worker"),
  worker("reconciler", { mode: "event+fallback" }),
  worker("scheduled-tasks", { mode: "event+fallback" }),
  worker("usage-ingest", { mode: "event" }),
];

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
            <Route path="/scheduled-tasks/internal/:worker" element={<ScheduledTasksPage />} />
            <Route path="/scheduled-tasks/:uid" element={<ScheduledTasksPage />} />
          </Routes>
          <Where />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function rows(region: string): string[] {
  return within(screen.getByRole("region", { name: region }))
    .getAllByRole("listitem")
    .map((li) => li.querySelector(".text-sm")?.textContent ?? "");
}

beforeEach(() => {
  api.list.mockResolvedValue([MORNING, FOLLOW_UP]);
  api.runs.mockResolvedValue([]);
  api.chats.mockResolvedValue([
    {
      channel: "ch-1",
      channel_name: "Work",
      chat_id: "owner",
      chat_kind: "direct",
      label: "Yuxing",
    },
    { channel: "ch-1", channel_name: "Work", chat_id: "grp", chat_kind: "group", label: "Release" },
  ]);
  vi.mocked(daemonApi.status).mockResolvedValue({
    runtime: { workers: WORKERS },
  } as unknown as Awaited<ReturnType<typeof daemonApi.status>>);
});
afterEach(() => vi.clearAllMocks());

describe("ScheduledTasksPage", () => {
  test("lists the owner's tasks and the agents' follow-ups apart, the first open", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Morning summary" })).toBeInTheDocument();
    expect(rows("My tasks")).toEqual(["Morning summary"]);
    expect(rows("Follow-ups")).toEqual(["Deploy check"]);
    expect(screen.getAllByText(/Every day at 09:00 · next/).length).toBeGreaterThan(0);
  });

  test("a follow-up says who it was booked for", async () => {
    renderPage("/scheduled-tasks/t-2");
    expect(await screen.findByRole("heading", { name: "Deploy check" })).toBeInTheDocument();
    expect(screen.getByText("Follow-up 1, booked by an agent for Sam")).toBeInTheDocument();
    expect(screen.getByText("Carries on the chat's conversation")).toBeInTheDocument();
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

  acceptance("channels", "a run's conversation opens from its history", async () => {
    const run = (id: string, over: Partial<ScheduledRun>): ScheduledRun => ({
      run_id: id,
      task_uid: "t-1",
      task_name: "Morning summary",
      due_at: "2026-10-29T09:00:00Z",
      started_at: "2026-10-29T09:00:00Z",
      finished_at: "2026-10-29T09:02:00Z",
      outcome: "replied",
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
    renderPage();
    const link = await screen.findByRole("link", { name: "Open pull requests" });
    expect(link).toHaveAttribute("href", "/conversations?open=c-2");
    expect(screen.getByText("Its conversation has been removed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Open in/ })).toBeNull();
  });

  acceptance("channels", "the page creates a task in a chosen chat", async () => {
    api.list.mockResolvedValue([]);
    api.create.mockResolvedValue(task({ uid: "t-new", name: "Weekly check" }));
    renderPage();
    expect(await screen.findByText("No scheduled tasks yet")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "New task" })[0]);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Weekly check" } });
    const chat = within(dialog).getByRole("combobox", { name: /Chat/ });
    await waitFor(() => expect(chat).not.toBeDisabled());
    fireEvent.keyDown(chat, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "Release · group" }));
    fireEvent.change(within(dialog).getByLabelText(/Prompt/), {
      target: { value: "List what shipped this week" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create task" }));
    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    expect(api.create.mock.calls[0][0]).toMatchObject({
      name: "Weekly check",
      config: {
        schedule: { kind: "daily", time: "09:00" },
        prompt: "List what shipped this week",
        chat: { channel: "ch-1", chat_id: "grp" },
        session: "fresh",
        catch_up: true,
      },
    });
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent("/scheduled-tasks/t-new"),
    );
  });

  acceptance("daemon", "the internal section lists the daemon's workers", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Morning summary" });
    // The featured workers, in the catalogue's order; the rest under Show all.
    expect(rows("Coffer internal")).toEqual(["Sync", "Reconciler", "Scheduled tasks"]);
    fireEvent.click(screen.getByRole("button", { name: "Show all (1 more)" }));
    expect(rows("Coffer internal")).toEqual([
      "Sync",
      "Reconciler",
      "Scheduled tasks",
      "Usage import",
    ]);
    fireEvent.click(
      within(screen.getByRole("region", { name: "Coffer internal" })).getByText("Sync"),
    );
    expect(screen.getByTestId("where")).toHaveTextContent("/scheduled-tasks/internal/sync-worker");
    expect(await screen.findByRole("heading", { name: "Sync" })).toBeInTheDocument();
    expect(screen.getByText("Runs on a timer")).toBeInTheDocument();
    // Read-only: nothing here runs or pauses a worker.
    expect(screen.queryByRole("button", { name: "Run now" })).not.toBeInTheDocument();
  });
});
