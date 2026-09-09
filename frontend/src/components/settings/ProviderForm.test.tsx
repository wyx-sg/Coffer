// frontend/src/components/settings/ProviderForm.test.tsx
// The compatible-agents picker: Coffer manages exactly two agent types, so the
// picker offers Claude Code and Codex and nothing else, and a ticked agent
// travels into the submitted body.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ProviderForm } from "./ProviderForm";

function renderForm(onSubmit = vi.fn()) {
  render(<ProviderForm pending={false} onSubmit={onSubmit} onCancel={() => {}} />);
  return onSubmit;
}

describe("ProviderForm compatible agents", () => {
  test("offers exactly the two managed agent types", () => {
    renderForm();
    expect(screen.getByRole("checkbox", { name: /claude code/i })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /codex/i })).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  });

  test("submits only the agent types the picker offers", () => {
    const onSubmit = renderForm();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "conn" } });
    fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: "sk-x" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const body = onSubmit.mock.calls[0][0];
    for (const a of body.compatible_agents as string[]) {
      expect(["claude_code", "codex"]).toContain(a);
    }
  });

  test("unticking an agent removes it from the submitted body", () => {
    const onSubmit = renderForm();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "conn" } });
    fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: "sk-x" } });
    const codex = screen.getByRole("checkbox", { name: /codex/i });
    if ((codex as HTMLInputElement).checked) {
      fireEvent.click(codex);
    }
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    const body = onSubmit.mock.calls[0][0];
    expect(body.compatible_agents).not.toContain("codex");
  });
});
