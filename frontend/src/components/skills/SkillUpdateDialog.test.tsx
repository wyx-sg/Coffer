// src/components/skills/SkillUpdateDialog.test.tsx
// Reviewing an update (canvas 4.3.18, 4.3.22): the 1060 change preview — what will happen, the
// changed files and their diffs, "Update to <commit>" — applying it, the conflict's two-way
// choice (Keep my edits / Take the update, with the diff of the side you are not keeping), and
// cancelling the stage on every other way out.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import { SkillUpdateDialog } from "./SkillUpdateDialog";
import { gitSkill, updatePreview } from "./skillSourceTestData";

vi.mock("@/lib/api/skills", () => ({
  skillsApi: {
    previewUpdate: vi.fn(),
    cancelStage: vi.fn(),
    applyUpdate: vi.fn(),
    keepMine: vi.fn(),
    compareUpdate: vi.fn(),
  },
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
const { skillsApi } = await import("@/lib/api/skills");
const api = vi.mocked(skillsApi);

const skill = gitSkill({ update_available: true, latest_commit: "f9e8d7c6b5a4" });

function renderDialog() {
  const onOpenChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SkillUpdateDialog skill={skill} open onOpenChange={onOpenChange} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

const conflicted = () =>
  updatePreview({
    conflict: true,
    local_changes: [
      {
        path: "SKILL.md",
        status: "modified",
        diff: "",
        binary: false,
        additions: 1,
        deletions: 1,
        truncated: false,
      },
    ],
  });

const COMPARE = {
  path: "SKILL.md",
  local: { text: "# Steps\n- my edit\n", binary: false, truncated: false },
  pinned: { text: "# Steps\n- base\n", binary: false, truncated: false },
  incoming: { text: "# Steps\n- their update\n", binary: false, truncated: false },
};

describe("SkillUpdateDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  test("previews what will happen, the changed files and their diffs", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview());
    renderDialog();
    expect(await screen.findByText("2 changes in Coffer")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Update terraform-plan" })).toHaveTextContent(
      "github.com/acme/agent-skills · terraform-plan/ · a1b2c3d → f9e8d7c",
    );
    expect(screen.getByText("What will happen")).toBeInTheDocument();
    // The commit count rides in Coffer's sentence; the subjects are not listed.
    expect(
      screen.getByText(/Moves terraform-plan from a1b2c3d to f9e8d7c \(2 commits\)/),
    ).toBeInTheDocument();
    expect(screen.getByText("Changes · 2")).toBeInTheDocument();
    const diff = screen.getByRole("region", { name: "Changes to SKILL.md" });
    expect(within(diff).getByText("- List replace, destroy or move.")).toBeInTheDocument();
    expect(diff.querySelector('[data-line="add"]')).not.toBeNull();
    expect(diff.querySelector('[data-line="remove"]')).not.toBeNull();
    expect(screen.getByRole("region", { name: "Changes to scripts/plan.sh" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Only terraform-plan changes. You can restore the pinned version from History.",
      ),
    ).toBeInTheDocument();
  });

  test("Update to applies the staged update and closes", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview());
    api.applyUpdate.mockResolvedValue(skill);
    const { onOpenChange } = renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: "Update to f9e8d7c" }));
    await waitFor(() =>
      expect(api.applyUpdate).toHaveBeenCalledWith("sk-1", {
        staging_id: "upd-1",
        discard_local_edits: false,
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(api.cancelStage).not.toHaveBeenCalled();
  });

  test("a refused apply stays in the dialog and the primary becomes Retry", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview());
    api.applyUpdate.mockRejectedValue(new ApiError("SKILL_SOURCE_UNREACHABLE", "git said no"));
    const { onOpenChange } = renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: "Update to f9e8d7c" }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  test("Cancel (a ghost button) cancels the stage and applies nothing", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview());
    const { onOpenChange } = renderDialog();
    const cancel = await screen.findByRole("button", { name: "Cancel" });
    expect(screen.queryByRole("button", { name: "Not now" })).not.toBeInTheDocument();
    fireEvent.click(cancel);
    await waitFor(() => expect(api.cancelStage).toHaveBeenCalledWith("upd-1"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.applyUpdate).not.toHaveBeenCalled();
  });

  test("an up-to-date source says so", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview({ up_to_date: true, changes: [] }));
    renderDialog();
    expect(await screen.findByText("Already up to date")).toBeInTheDocument();
  });

  test("a conflict is the two-way choice: Keep my edits or Take the update, nothing else", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    api.compareUpdate.mockResolvedValue(COMPARE);
    renderDialog();
    const dialog = await screen.findByRole("dialog", {
      name: "terraform-plan changed on both sides",
    });
    expect(within(dialog).getAllByRole("radio")).toHaveLength(2);
    expect(within(dialog).getByRole("radio", { name: /Keep my edits/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /Take the update/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.queryByRole("radio", { name: /Merge with an agent/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Compare" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Update to f9e8d7c" })).not.toBeInTheDocument();
    expect(within(dialog).getByText("Nothing is written until you choose.")).toBeInTheDocument();
    // The diff is your version → the update.
    const diff = await screen.findByRole("region", { name: "Changes to SKILL.md" });
    expect(within(diff).getByText("- their update")).toBeInTheDocument();
    expect(within(dialog).getByText(/your version → the update/)).toBeInTheDocument();
  });

  test("choosing Keep my edits flips the diff and the primary", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    api.compareUpdate.mockResolvedValue(COMPARE);
    renderDialog();
    fireEvent.click(await screen.findByRole("radio", { name: /Keep my edits/ }));
    expect(screen.getByText(/the update → your version/)).toBeInTheDocument();
    const diff = await screen.findByRole("region", { name: "Changes to SKILL.md" });
    expect(within(diff).getByText("- my edit")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep my edits" })).toBeInTheDocument();
  });

  test("Keep my edits keeps the new commit off and cancels the stage", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    api.compareUpdate.mockResolvedValue(COMPARE);
    api.keepMine.mockResolvedValue(skill.source_status!);
    const { onOpenChange } = renderDialog();
    fireEvent.click(await screen.findByRole("radio", { name: /Keep my edits/ }));
    fireEvent.click(screen.getByRole("button", { name: "Keep my edits" }));
    await waitFor(() => expect(api.keepMine).toHaveBeenCalledWith("sk-1", "f9e8d7c6b5a4"));
    await waitFor(() => expect(api.cancelStage).toHaveBeenCalledWith("upd-1"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.applyUpdate).not.toHaveBeenCalled();
  });

  test("Take the update applies it discarding the local edits — the dialog is the confirmation", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    api.compareUpdate.mockResolvedValue(COMPARE);
    api.applyUpdate.mockResolvedValue(skill);
    const { onOpenChange } = renderDialog();
    await screen.findByRole("radio", { name: /Take the update/ });
    fireEvent.click(screen.getByRole("button", { name: "Take the update" }));
    await waitFor(() =>
      expect(api.applyUpdate).toHaveBeenCalledWith("sk-1", {
        staging_id: "upd-1",
        discard_local_edits: true,
      }),
    );
    expect(screen.queryByRole("dialog", { name: "Discard your edits?" })).not.toBeInTheDocument();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
