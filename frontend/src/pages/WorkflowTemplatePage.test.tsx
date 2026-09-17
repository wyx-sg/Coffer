// frontend/src/pages/WorkflowTemplatePage.test.tsx
//
// The editor, tested through the real hooks against a mocked API CLIENT rather
// than mocked hooks: two of the three things that matter here are facts about
// the request the editor makes (it goes through the resource endpoint, and it
// carries exactly the template that was authored — FR-054/FR-056), and a test
// that stubbed the mutation could not see either.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { WorkflowTemplatePage } from "./WorkflowTemplatePage";
import { acceptance } from "@/test/acceptance";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { TemplateConfig } from "@/lib/api/workflow";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
// The two vault lists the pickers offer. Mocked at the hook so this file's
// network boundary stays the one request it is asserting on.
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: () => ({ data: [{ name: "coffer-writing-td" }] }),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({ data: [{ name: "claude_code" }] }),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

/** A node exactly as the editor writes one. */
function node(key: string, name: string, type: "ai" | "manual" = "ai") {
  return {
    key,
    name,
    type,
    skill: null,
    instructions: null,
    artifacts: [],
    approval: "never",
    on_failure: { action: "stop" },
    agent: null,
  };
}

/** Design → Coding → Testing, with testing sending work back to coding. */
function threeStages(): TemplateConfig {
  return {
    description: null,
    attempt_ceiling: 3,
    stages: [
      {
        key: "tech_design",
        name: "Tech Design",
        optional: false,
        nodes: [node("draft_td", "Draft the TD")],
      },
      {
        key: "coding",
        name: "Coding",
        optional: false,
        nodes: [node("implement", "Implement")],
      },
      {
        key: "testing",
        name: "Testing",
        optional: false,
        nodes: [node("verify", "Verify")],
      },
    ],
    edges: [{ from_stage: "testing", to_stage: "coding", reason: "code_issue" }],
  } as TemplateConfig;
}

function resource(config: TemplateConfig) {
  return {
    ref: "workflow:delivery",
    kind: "workflow",
    name: "delivery",
    description: null,
    config,
    enabled: true,
    created_at: "2026-09-17T00:00:00Z",
    updated_at: "2026-09-17T00:00:00Z",
  };
}

let api: ApiClientMock;

/**
 * A STATEFUL fake: GET returns whatever the last PATCH stored.
 *
 * The editor holds no draft — each edit is computed from what the cache holds
 * and written straight back (FR-062) — so a fake that always replayed the
 * original config would make every edit look like the first one and would
 * hide exactly the bug that costs a developer their work.
 */
function mount(config: TemplateConfig, { search = "" }: { search?: string } = {}) {
  let stored = config;
  api.GET = vi
    .fn()
    .mockImplementation(() => Promise.resolve({ data: resource(stored), error: undefined }));
  api.PATCH = vi
    .fn()
    .mockImplementation((_path: string, opts: { body: { config: TemplateConfig } }) => {
      stored = opts.body.config;
      return Promise.resolve({ data: undefined, error: undefined });
    });
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/workflows/delivery${search}`]}>
          <Routes>
            <Route path="/workflows/:name" element={<WorkflowTemplatePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** Drill from the stage diagram into one stage's own diagram (FR-061). */
async function openStage(key: string) {
  fireEvent.click(await screen.findByTestId(`stage-${key}`));
}

/** Pick `option` in the Radix select the label points at. */
async function choose(trigger: HTMLElement, option: string) {
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByRole("option", { name: option }));
}

beforeEach(() => {
  api = mockApiClient();
});
afterEach(() => vi.clearAllMocks());

/** The config the editor PATCHed, from the last write it made. */
function written(): TemplateConfig {
  const calls = vi.mocked(api.PATCH).mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  const last = calls[calls.length - 1][1] as { body: { config: TemplateConfig } };
  return last.body.config;
}

describe("WorkflowTemplatePage", () => {
  acceptance("workflow", "the editor shows the shape one depth at a time", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    // Every stage, and the reason that sends work back drawn beside them.
    expect(screen.getByText("Tech Design")).toBeInTheDocument();
    expect(screen.getByText("Coding")).toBeInTheDocument();
    expect(screen.getByText("code_issue")).toBeInTheDocument();

    // Not the tasks inside them — that is the next question, not this one.
    expect(screen.queryByTestId("task-draft_td")).not.toBeInTheDocument();
    // And not one of the fields the old inline editor put on screen.
    expect(screen.queryByLabelText("Instructions")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Skill")).not.toBeInTheDocument();

    // One depth in: this stage's tasks, and no other stage's.
    await openStage("tech_design");
    expect(await screen.findByTestId("task-draft_td")).toHaveTextContent("Draft the TD");
    expect(screen.queryByTestId("task-implement")).not.toBeInTheDocument();

    // One depth further: that task's fields.
    fireEvent.click(screen.getByTestId("task-draft_td"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Skill")).toBeInTheDocument();
  });

  test("a stage opens onto its own tasks, and the way back is named", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    await openStage("tech_design");
    expect(await screen.findByTestId("task-draft_td")).toHaveTextContent("Draft the TD");
    // One stage at a time: the other stages' tasks are not on screen either.
    expect(screen.queryByTestId("task-implement")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All stages" }));
    expect(await screen.findByTestId("stage-coding")).toBeInTheDocument();
    expect(screen.queryByTestId("task-draft_td")).not.toBeInTheDocument();
  });

  acceptance("workflow", "the editor never asks for an identifier it can derive", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    // Not on the map…
    expect(screen.queryByLabelText("Key")).not.toBeInTheDocument();
    // …and not in either dialog.
    await openStage("tech_design");
    fireEvent.click(await screen.findByTestId("task-draft_td"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByLabelText("Key")).not.toBeInTheDocument();
  });

  acceptance("workflow", "the editor has no save button of its own", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    expect(screen.queryByRole("button", { name: "Save workflow" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Discard changes" })).not.toBeInTheDocument();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });

  acceptance("workflow", "a template is authored in the app", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    // Open the task, change what it runs, save in the dialog.
    await openStage("tech_design");
    fireEvent.click(await screen.findByTestId("task-draft_td"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Task"), {
      target: { value: "Draft the technical design" },
    });
    await choose(within(dialog).getByLabelText("Skill"), "coffer-writing-td");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    // Through the resource endpoint, like every other client of every other
    // kind (FR-056) — the editor has no write path of its own.
    expect(vi.mocked(api.PATCH).mock.calls[0][0]).toBe("/resources/{kind}/{name}");

    const config = written();
    expect(config.stages[0].nodes[0].name).toBe("Draft the technical design");
    expect(config.stages[0].nodes[0].skill).toBe("coffer-writing-td");
    // The key came from the name; nobody typed it.
    expect(config.stages[0].nodes[0].key).toBe("draft_the_technical_design");
  });

  test("a stage's dialog holds its feedback edge, and there is no edges tab", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    expect(screen.queryByRole("tab", { name: "Feedback" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit stage Testing" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByDisplayValue("code_issue")).toBeInTheDocument();
  });

  test("a second edit made before the first has come back builds on it", async () => {
    // The settings fields save on blur and have no in-flight guard — you can
    // leave one field and the next within a few milliseconds, long before the
    // refetch that follows the first save has landed. With no draft, each edit
    // is computed from what the cache HOLDS, so unless a save writes its own
    // result there, the second edit is computed from the pre-save config and
    // silently undoes the first.
    mount(threeStages(), { search: "?tab=settings" });
    const ceiling = await screen.findByLabelText("Attempt ceiling");
    const budget = screen.getByLabelText("Token budget");

    fireEvent.change(ceiling, { target: { value: "7" } });
    fireEvent.blur(ceiling);
    fireEvent.change(budget, { target: { value: "120000" } });
    fireEvent.blur(budget);

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(2));
    const config = written();
    expect(config.token_budget).toBe(120000);
    // The one that matters: the ceiling is still 7 and not back at 3.
    expect(config.attempt_ceiling).toBe(7);
  });

  test("deleting a stage writes the template without it", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    fireEvent.click(screen.getByRole("button", { name: "Remove stage Coding" }));

    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    const config = written();
    expect(config.stages.map((s) => s.key)).toEqual(["tech_design", "testing"]);
    // …and the edge that named it, which would otherwise refuse the next save.
    expect(config.edges).toEqual([]);
  });

  test("a task is deleted from its box, and the only one in a stage is not", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    // Deleting is an act on the box, so it is on the box — and the dialog
    // holds a task's FIELDS and nothing else.
    await openStage("tech_design");
    fireEvent.click(await screen.findByTestId("task-draft_td"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: /Delete task/ })).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    // A stage with no tasks is refused by the contract and the engine reads
    // `stage.nodes[0]`; the stage is what you delete instead.
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("button", { name: "Delete task Draft the TD" })).toBeDisabled();
  });

  acceptance(
    "workflow",
    "an invalid template is refused against the field that is wrong",
    async () => {
      mount(threeStages());
      await screen.findByRole("heading", { name: "delivery" });
      api.PATCH = vi.fn().mockResolvedValue({
        data: undefined,
        error: {
          error: {
            code: "RESOURCE_INVALID",
            message: "stages[0].nodes[0].skill: no registered skill named 'gone'",
            details: { path: "stages[0].nodes[0].skill" },
          },
        },
      });

      await openStage("tech_design");
      fireEvent.click(await screen.findByTestId("task-draft_td"));
      const dialog = await screen.findByRole("dialog");
      fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

      const message = await screen.findByText(/no registered skill named 'gone'/);
      // Against the field the refusal named, not in a banner over the form.
      expect(message.id).toBe("template-error-stages[0].nodes[0].skill");
      // And the dialog is still open, holding what was typed.
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    },
  );
});
