import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";

import { ConfirmDialog } from "./confirm-dialog";

function renderDialog(overrides: Partial<React.ComponentProps<typeof ConfirmDialog>> = {}) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      title="Delete this conversation?"
      description="This cannot be undone."
      confirmLabel="Delete"
      onConfirm={onConfirm}
      {...overrides}
    />,
  );
  return { onConfirm, onOpenChange };
}

describe("ConfirmDialog", () => {
  test("shows the title, description, and confirm label", () => {
    renderDialog();
    expect(screen.getByText("Delete this conversation?")).toBeInTheDocument();
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  test("calls onConfirm when the confirm button is clicked", () => {
    const { onConfirm } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  test("cancel closes via onOpenChange(false) without confirming", () => {
    const { onConfirm, onOpenChange } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("confirm button is disabled while pending", () => {
    renderDialog({ pending: true });
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
  });
});

// The convention: a confirmation closes only on success. Two call sites used to
// answer that differently — a hand-rolled Dialog with its own inline error, and
// a caller that closed whatever happened — so the rule is pinned on the
// primitive that now owns it.
describe("ConfirmDialog closes only on success", () => {
  test("a resolving onConfirm closes the dialog", async () => {
    const { onOpenChange } = renderDialog({ onConfirm: () => Promise.resolve() });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a rejecting onConfirm keeps it open and shows the reason", async () => {
    const { onOpenChange } = renderDialog({
      onConfirm: () => Promise.reject(new ApiError("RESOURCE_IN_USE", "still referenced")),
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    // The raw code is never what the user reads.
    expect(screen.queryByText("RESOURCE_IN_USE")).toBeNull();
  });

  test("a void onConfirm leaves the closing to the caller", () => {
    const { onConfirm, onOpenChange } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  test("a caller-supplied error is shown inline, so the dialog is never mute", () => {
    renderDialog({ error: new ApiError("RESOURCE_IN_USE", "still referenced") });
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  test("no error, no alert", () => {
    renderDialog();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
