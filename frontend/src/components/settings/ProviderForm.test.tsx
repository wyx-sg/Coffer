// frontend/src/components/settings/ProviderForm.test.tsx
// The compatible-agents picker: selectable agents toggle in and out of the
// submitted body, and a never-projectable agent (cursor — no endpoint setting
// upstream) is omitted from the list outright and never submitted; its "not
// supported" reason lives on the agent's own detail page (ADR-042 presentation
// amendment 2026-07-10, FR-003a).
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ProviderForm } from "./ProviderForm";

function renderForm(onSubmit = vi.fn()) {
  render(<ProviderForm pending={false} onSubmit={onSubmit} onCancel={() => {}} />);
  return onSubmit;
}

describe("ProviderForm compatible agents", () => {
  test("cursor does not appear in the picker at all", () => {
    renderForm();
    expect(screen.queryByRole("checkbox", { name: /cursor/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/locked to cursor's own backend/i)).not.toBeInTheDocument();
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
