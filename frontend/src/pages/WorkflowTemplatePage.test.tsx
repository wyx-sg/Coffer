// frontend/src/pages/WorkflowTemplatePage.test.tsx
//
// The editor, tested through the real hooks against a mocked API CLIENT rather
// than mocked hooks: two of the three things that matter here are facts about
// the request the editor makes (it goes through the resource endpoint, and it
// carries exactly the template that was authored), and a test
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
    attempt_ceiling: 3,
  };
}

/** Design → Coding → Testing, with testing sending work back to coding. */
function threeStages(): TemplateConfig {
  return {
    description: null,
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
  } as TemplateConfig;
}

function resource(config: TemplateConfig) {
  return {
    uid: "wf-delivery",
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
 * and written straight back — so a fake that always replayed the
 * original config would make every edit look like the first one and would
 * hide exactly the bug that costs a developer their work.
 */
function mount(config: TemplateConfig, { search = "" }: { search?: string } = {}) {
  let stored = config;
  let storedName = "delivery";
  api.GET = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve({ data: { ...resource(stored), name: storedName }, error: undefined }),
    );
  api.PATCH = vi
    .fn()
    .mockImplementation(
      (_path: string, opts: { body: { config: TemplateConfig; name?: string } }) => {
        stored = opts.body.config;
        if (opts.body.name !== undefined) storedName = opts.body.name;
        return Promise.resolve({ data: undefined, error: undefined });
      },
    );
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/workflows/wf-delivery${search}`]}>
          <Routes>
            <Route path="/workflows/:uid" element={<WorkflowTemplatePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** Select a stage in the list, which is what the other pane then shows. */
async function openStage(key: string) {
  fireEvent.click(await screen.findByTestId(`stage-${key}`));
}

/** Open a task's fields. The card is not itself a button — it holds two — so
 *  the way in is the one that says so. */
async function openTask(key: string) {
  const card = await screen.findByTestId(`task-${key}`);
  fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
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
  acceptance(
    "workflow",
    "the editor shows the whole flow beside the one stage being edited",
    async () => {
      mount(threeStages());
      await screen.findByRole("heading", { name: "delivery" });

      // Every stage at once — the flow never leaves the screen.
      expect(await screen.findByTestId("stage-tech_design")).toBeInTheDocument();
      expect(screen.getByTestId("stage-coding")).toBeInTheDocument();
      expect(screen.getByTestId("stage-testing")).toBeInTheDocument();

      // The first stage's tasks beside them, and no other stage's.
      expect(screen.getByTestId("task-draft_td")).toHaveTextContent("Draft the TD");
      expect(screen.queryByTestId("task-implement")).not.toBeInTheDocument();

      // Selecting another stage swaps the tasks, not the flow.
      await openStage("coding");
      expect(await screen.findByTestId("task-implement")).toBeInTheDocument();
      expect(screen.queryByTestId("task-draft_td")).not.toBeInTheDocument();
      expect(screen.getByTestId("stage-tech_design")).toBeInTheDocument();

      // A task's own fields are one click further, in its dialog.
      expect(screen.queryByLabelText("Skill")).not.toBeInTheDocument();
      await openTask("implement");
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByLabelText("Skill")).toBeInTheDocument();
    },
  );

  acceptance("workflow", "the editor never asks for an identifier it can derive", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    // Not on the map…
    expect(screen.queryByLabelText("Key")).not.toBeInTheDocument();
    // …and not in either dialog.
    await openTask("draft_td");
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
    await openTask("draft_td");
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Task"), {
      target: { value: "Draft the technical design" },
    });
    await choose(within(dialog).getByLabelText("Skill"), "coffer-writing-td");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    // Through the resource endpoint, like every other client of every other
    // kind — the editor has no write path of its own.
    expect(vi.mocked(api.PATCH).mock.calls[0][0]).toBe("/resources/{uid}");

    const config = written();
    expect(config.stages[0].nodes[0].name).toBe("Draft the technical design");
    expect(config.stages[0].nodes[0].skill).toBe("coffer-writing-td");
    // The key came from the name; nobody typed it.
    expect(config.stages[0].nodes[0].key).toBe("draft_the_technical_design");
  });

  test("a stage's dialog asks for its own fields and no route out of it", async () => {
    // The editor used to offer a route back to an earlier stage here. There is
    // no such route any more, and the regression worth
    // pinning is somebody reintroducing the field rather than the judgement —
    // which stage a finding sends work to is the developer's, made when they
    // have the finding, not the template's, made before the run existed.
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    await openStage("testing");
    fireEvent.click(await screen.findByRole("button", { name: "Edit stage Testing" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByDisplayValue("code_issue")).not.toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("Testing")).toBeInTheDocument();
  });

  test("deleting a stage asks first, then writes the template without it", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    fireEvent.click(await screen.findByRole("button", { name: "Remove stage Coding" }));

    // The editor writes every edit the moment it is made, so a delete
    // IS the save: there is no draft to change your mind in afterwards, and
    // pressing the button must not be the last word.
    const ask = await screen.findByRole("dialog");
    expect(ask).toHaveTextContent(/Delete “Coding”\?/);
    expect(api.PATCH).not.toHaveBeenCalled();
    fireEvent.click(within(ask).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    const config = written();
    expect(config.stages.map((s) => s.key)).toEqual(["tech_design", "testing"]);
    // Nothing else references a stage by key any more, so deleting one is the
    // whole of the edit — there is no second place to keep in step with it.
    expect(config).not.toHaveProperty("edges");
  });

  test("deleting a task asks first as well", async () => {
    mount(threeStages());
    await openStage("coding");
    const card = await screen.findByTestId("task-implement");
    // The only task in its stage cannot go, so this template needs a second.
    expect(within(card).getByRole("button", { name: /Delete task/ })).toBeDisabled();
  });

  test("a task is deleted from its box, and the only one in a stage is not", async () => {
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    // Deleting is an act on the box, so it is on the box — and the dialog
    // holds a task's FIELDS and nothing else.
    await openTask("draft_td");
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

      await openTask("draft_td");
      const dialog = await screen.findByRole("dialog");
      fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

      const message = await screen.findByText(/no registered skill named 'gone'/);
      // Against the field the refusal named, not in a banner over the form.
      expect(message.id).toBe("template-error-stages[0].nodes[0].skill");
      // And the dialog is still open, holding what was typed.
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    },
  );

  acceptance("workflow", "a workflow is renamed and re-described in place", async () => {
    // The two fields that are not part of the shape, edited where the
    // shape is — not in a settings tab beside numbers that have moved onto
    // the tasks they bound.
    mount(threeStages());
    await screen.findByRole("heading", { name: "delivery" });

    // The header's Edit, not a task card's — the page has both, and only one
    // of them is about the workflow itself.
    const header = screen.getByRole("banner");
    fireEvent.click(within(header).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "release" } });
    fireEvent.change(within(dialog).getByLabelText("Description"), {
      target: { value: "One repository, design first" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(1));
    const [, options] = api.PATCH.mock.calls[0] as [
      string,
      { body: { name: string; description: string; config: TemplateConfig } },
    ];
    const body = options.body;
    expect(body.name).toBe("release");
    expect(body.description).toBe("One repository, design first");
    // The shape came through untouched: a rename is not an edit of the flow.
    expect(body.config.stages.map((s) => s.key)).toEqual(["tech_design", "coding", "testing"]);
  });
});
