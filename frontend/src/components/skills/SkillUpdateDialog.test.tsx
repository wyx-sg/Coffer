// src/components/skills/SkillUpdateDialog.test.tsx
// Reviewing an update: the preview, applying it, the conflict's three choices, and cancelling the stage on every other way out.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { SkillUpdateDialog } from "./SkillUpdateDialog";
import { gitSkill, updatePreview } from "./skillSourceTestData";

vi.mock("@/lib/api/skills", () => ({
  skillsApi: {
    previewUpdate: vi.fn(),
    cancelStage: vi.fn(),
    applyUpdate: vi.fn(),
    keepMine: vi.fn(),
    markMerged: vi.fn(),
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

const MERGE_PROMPT = "Skill terraform-plan has local edits, and its source has an update.";

const conflicted = () =>
  updatePreview({
    conflict: true,
    handoff: { prompt: MERGE_PROMPT },
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

describe("SkillUpdateDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  test("previews the range, the commits, the changed files and the selected diff", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview());
    renderDialog();
    expect(await screen.findByText(/“Ask before backend changes”/)).toBeInTheDocument();
    expect(screen.getByText("What will happen")).toBeInTheDocument();
    expect(screen.getByText(/Moves terraform-plan from a1b2c3d to f9e8d7c/)).toBeInTheDocument();
    expect(screen.getByText("Changes · 2", { selector: "span" })).toBeInTheDocument();
    const diff = screen.getByRole("region", { name: "Changes to SKILL.md" });
    expect(within(diff).getByText("- List replace, destroy or move.")).toBeInTheDocument();
    expect(diff.querySelector('[data-line="add"]')).not.toBeNull();
    expect(diff.querySelector('[data-line="remove"]')).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /scripts\/plan\.sh/ }));
    expect(screen.getByRole("region", { name: "Changes to scripts/plan.sh" })).toBeInTheDocument();
    expect(screen.getByText("Only terraform-plan changes.")).toBeInTheDocument();
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

  test("Not now cancels the stage and applies nothing", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview());
    const { onOpenChange } = renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
    await waitFor(() => expect(api.cancelStage).toHaveBeenCalledWith("upd-1"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.applyUpdate).not.toHaveBeenCalled();
  });

  test("an up-to-date source says so", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview({ up_to_date: true, changes: [] }));
    renderDialog();
    expect(await screen.findByText("Already up to date")).toBeInTheDocument();
  });

  test("a conflict offers Keep my edits, Take the update and Compare", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    renderDialog();
    expect(
      await screen.findByRole("dialog", { name: "terraform-plan changed on both sides" }),
    ).toBeInTheDocument();
    const edits = screen.getByLabelText("Files you edited");
    expect(within(edits).getByText("SKILL.md")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Keep my edits/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Take the update/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Update to f9e8d7c" })).not.toBeInTheDocument();
  });

  test("Keep my edits keeps the new commit off and cancels the stage", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    api.keepMine.mockResolvedValue(skill.source_status!);
    const { onOpenChange } = renderDialog();
    fireEvent.click(await screen.findByRole("radio", { name: /Keep my edits/ }));
    fireEvent.click(screen.getByRole("button", { name: "Keep my edits" }));
    await waitFor(() => expect(api.keepMine).toHaveBeenCalledWith("sk-1", "f9e8d7c6b5a4"));
    await waitFor(() => expect(api.cancelStage).toHaveBeenCalledWith("upd-1"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.applyUpdate).not.toHaveBeenCalled();
  });

  test("Take the update asks first, then applies discarding the local edits", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    api.applyUpdate.mockResolvedValue(skill);
    const { onOpenChange } = renderDialog();
    fireEvent.click(await screen.findByRole("radio", { name: /Take the update/ }));
    fireEvent.click(screen.getByRole("button", { name: "Take the update" }));
    const confirm = await screen.findByRole("dialog", { name: "Discard your edits?" });
    expect(api.applyUpdate).not.toHaveBeenCalled();
    fireEvent.click(within(confirm).getByRole("button", { name: "Take the update" }));
    await waitFor(() =>
      expect(api.applyUpdate).toHaveBeenCalledWith("sk-1", {
        staging_id: "upd-1",
        discard_local_edits: true,
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  acceptance("skill-manager", "a conflict hands merging the update to an agent", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    api.previewUpdate.mockResolvedValue(conflicted());
    renderDialog();
    fireEvent.click(await screen.findByRole("radio", { name: /Merge with an agent/ }));
    const box = screen.getByTestId("skill-update-merge-handoff");
    fireEvent.click(within(box).getByRole("button", { name: "Copy prompt" }));
    expect(writeText).toHaveBeenCalledWith(MERGE_PROMPT);
    // The two manual choices stay.
    expect(screen.getByRole("radio", { name: /Keep my edits/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Take the update/ })).toBeInTheDocument();
  });

  acceptance(
    "skill-manager",
    "recording a merge moves the pin and keeps the merged files",
    async () => {
      api.previewUpdate.mockResolvedValue(conflicted());
      api.markMerged.mockResolvedValue(skill);
      const { onOpenChange } = renderDialog();
      fireEvent.click(await screen.findByRole("radio", { name: /Merge with an agent/ }));
      fireEvent.click(screen.getByRole("button", { name: "I merged it" }));
      const confirm = await screen.findByRole("dialog", { name: "Record the merge?" });
      expect(api.markMerged).not.toHaveBeenCalled();
      fireEvent.click(within(confirm).getByRole("button", { name: "I merged it" }));
      await waitFor(() => expect(api.markMerged).toHaveBeenCalledWith("sk-1", "f9e8d7c6b5a4"));
      await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
      expect(api.cancelStage).toHaveBeenCalledWith("upd-1");
      expect(api.applyUpdate).not.toHaveBeenCalled();
    },
  );

  test("without a hand-off there is no merge choice", async () => {
    api.previewUpdate.mockResolvedValue({ ...conflicted(), handoff: null });
    renderDialog();
    expect(await screen.findByRole("radio", { name: /Keep my edits/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Merge with an agent/ })).not.toBeInTheDocument();
  });

  test("Compare shows the local, pinned and new versions of a file", async () => {
    api.previewUpdate.mockResolvedValue(conflicted());
    api.compareUpdate.mockResolvedValue({
      path: "SKILL.md",
      local: { text: "mine", binary: false, truncated: false },
      pinned: { text: "base", binary: false, truncated: false },
      incoming: { text: "theirs", binary: false, truncated: false },
    });
    renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: "Compare" }));
    await waitFor(() =>
      expect(api.compareUpdate).toHaveBeenCalledWith("sk-1", "upd-1", "SKILL.md"),
    );
    expect(await screen.findByText("mine")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Pinned" })).getByText("base"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "New" })).getByText("theirs"),
    ).toBeInTheDocument();
  });
});
