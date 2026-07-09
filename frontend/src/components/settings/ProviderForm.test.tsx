// frontend/src/components/settings/ProviderForm.test.tsx
// The compatible-agents picker: selectable agents toggle in and out of the
// submitted body, and an unprojectable agent (cursor — no endpoint setting
// upstream) is surfaced as a disabled checkbox with the reason, never silently
// omitted and never submitted (ADR-042).
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ProviderForm } from "./ProviderForm";

function renderForm(onSubmit = vi.fn()) {
  render(<ProviderForm pending={false} onSubmit={onSubmit} onCancel={() => {}} />);
  return onSubmit;
}

describe("ProviderForm compatible agents", () => {
  test("cursor renders as a disabled checkbox with the reason text", () => {
    renderForm();
    const cursorBox = screen.getByRole("checkbox", { name: /cursor/i });
    expect(cursorBox).toBeDisabled();
    expect(cursorBox).not.toBeChecked();
    expect(screen.getByText(/locked to cursor's own backend/i)).toBeInTheDocument();
  });

  test("submitting never includes an unprojectable agent", async () => {
    const onSubmit = renderForm();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "conn" } });
    fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: "sk-x" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const body = onSubmit.mock.calls[0][0];
    expect(body.compatible_agents).not.toContain("cursor");
  });
});
