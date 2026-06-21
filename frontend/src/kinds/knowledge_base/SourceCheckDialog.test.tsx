// frontend/src/kinds/knowledge_base/SourceCheckDialog.test.tsx
//
// The source-check report dialog: each of the five statuses renders its label,
// the "Update from source" action appears ONLY for `changed` rows (and calls
// onUpdate with the right document id), and an empty report shows the
// web-uploads-aren't-tracked explanation.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { SourceCheckDialog } from "./SourceCheckDialog";
import type { SourceCheckResponse } from "./api";

const REPORT: SourceCheckResponse = {
  sources: [
    { document_id: "d-unchanged", title: "Stable", source_path: "/a/stable.md", status: "unchanged" },
    { document_id: "d-changed", title: "Drifted", source_path: "/a/drifted.md", status: "changed" },
    { document_id: "d-missing", title: "Gone", source_path: "/a/gone.md", status: "missing" },
    { document_id: "d-edited", title: "Tweaked", source_path: "/a/tweaked.md", status: "edited" },
    { document_id: "d-updated", title: "Fresh", source_path: "/a/fresh.md", status: "updated" },
  ],
};

function renderDialog(overrides: Partial<React.ComponentProps<typeof SourceCheckDialog>> = {}) {
  const onUpdate = vi.fn();
  render(
    <SourceCheckDialog
      open
      onOpenChange={() => {}}
      report={REPORT}
      updatingId={null}
      onUpdate={onUpdate}
      {...overrides}
    />,
  );
  return { onUpdate };
}

describe("SourceCheckDialog", () => {
  test("renders a status label for each of the five statuses", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Up to date")).toBeVisible();
    expect(within(dialog).getByText("Source changed")).toBeVisible();
    expect(within(dialog).getByText("Source missing")).toBeVisible();
    expect(within(dialog).getByText("Locally edited")).toBeVisible();
    expect(within(dialog).getByText("Auto-updated")).toBeVisible();
  });

  test("shows the missing + edited per-row notes", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/source file not found/i)).toBeVisible();
    expect(within(dialog).getByText(/edited locally/i)).toBeVisible();
  });

  test("offers 'Update from source' only for changed rows", () => {
    renderDialog();
    const updateButtons = screen.getAllByRole("button", { name: /update from source/i });
    expect(updateButtons).toHaveLength(1);
  });

  test("clicking Update calls onUpdate with that row's document id", () => {
    const { onUpdate } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: /update from source/i }));
    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onUpdate).toHaveBeenCalledWith("d-changed");
  });

  test("disables the update button while that row is updating", () => {
    renderDialog({ updatingId: "d-changed" });
    expect(screen.getByRole("button", { name: /update from source/i })).toBeDisabled();
  });

  test("an empty report shows the untracked-web-uploads message", () => {
    renderDialog({ report: { sources: [] } });
    expect(screen.getByText(/web uploads aren't tracked/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: /update from source/i })).toBeNull();
  });
});
