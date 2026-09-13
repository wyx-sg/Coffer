// frontend/src/components/settings/ProviderForm.test.tsx
//
// The regression these tests exist for: the form used to carry compatible-agents
// checkboxes and send `compatible_agents` in its create and patch bodies. That
// key is gone from the request schemas — the axis is the resource's per-agent
// SCOPE now — and Pydantic IGNORES unknown fields, so the request kept
// succeeding while the user's choice was silently thrown away. Nothing rendered
// differently, which is exactly why a render-only test would have missed it.
//
// So the assertions are on the BODY: neither the create body nor the patch body
// may carry `compatible_agents`, for any wire. The reach control is deliberately
// absent from this dialog (the row's and the detail header's ScopeControl own
// it), and the form says so with a hint.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ProviderForm } from "./ProviderForm";
import type { Provider } from "@/lib/api/providers";

function renderCreate(onSubmit = vi.fn()) {
  render(<ProviderForm pending={false} onSubmit={onSubmit} onCancel={() => {}} />);
  return onSubmit;
}

const existing = (overrides?: Partial<Provider>): Provider => ({
  name: "acme",
  protocol: "openai",
  base_url: "https://gw/v1",
  credential_ref: "provider/acme/key",
  compatible_agents: ["codex"],
  is_active: false,
  internal_default: false,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  ...overrides,
});

function renderEdit(onUpdate = vi.fn()) {
  render(
    <ProviderForm
      initial={existing()}
      pending={false}
      onSubmit={vi.fn()}
      onUpdate={onUpdate}
      onCancel={() => {}}
    />,
  );
  return onUpdate;
}

function fillAndSave() {
  fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "conn" } });
  fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: "sk-x" } });
  fireEvent.click(screen.getByRole("button", { name: /save/i }));
}

describe("ProviderForm no longer writes compatible_agents", () => {
  test("the create body carries no compatible_agents", () => {
    const onSubmit = renderCreate();
    fillAndSave();
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const body = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(body).not.toHaveProperty("compatible_agents");
    // The fields that DO belong to a connection still travel.
    expect(body).toMatchObject({ name: "conn", protocol: "openai", secret_value: "sk-x" });
  });

  test("the create body carries no compatible_agents for a keyless wire either", () => {
    const onSubmit = renderCreate();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "local" } });
    fireEvent.change(screen.getByLabelText(/vendor/i), { target: { value: "ollama" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    const body = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(body).not.toHaveProperty("compatible_agents");
    expect(body).toMatchObject({ protocol: "ollama" });
  });

  test("the patch body carries no compatible_agents", () => {
    const onUpdate = renderEdit();
    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: "https://gw2/v1" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onUpdate).toHaveBeenCalledTimes(1);
    const patch = onUpdate.mock.calls[0][0] as Record<string, unknown>;
    expect(patch).not.toHaveProperty("compatible_agents");
    expect(patch).toMatchObject({ base_url: "https://gw2/v1" });
  });

  test("the dialog offers no agent picker — reach is the scope control's, and it says so", () => {
    renderCreate();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryByText(/compatible agents/i)).not.toBeInTheDocument();
    expect(screen.getByText(/reach control/i)).toBeInTheDocument();
  });
});
