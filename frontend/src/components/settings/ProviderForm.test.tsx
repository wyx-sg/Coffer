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
//
// Validation is zod (react-hook-form) rather than the browser's `required`, so
// a blank name or a bare hostname is refused with a translated message under
// the field and nothing is submitted.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ProviderForm } from "./ProviderForm";
import type { Provider } from "@/lib/api/providers";

function renderCreate(onSubmit = vi.fn()) {
  render(<ProviderForm pending={false} onSubmit={onSubmit} onCancel={() => {}} />);
  return onSubmit;
}

const existing = (overrides?: Partial<Provider>): Provider => ({
  // The form never sends the uid — it hands its caller a patch and, when the
  // label changed, the new name — but a `Provider` carries one, so the fixture
  // does too.
  uid: "cn-31f0",
  name: "acme",
  protocol: "openai",
  base_url: "https://gw/v1",
  credential_ref: "provider/acme/key",
  compatible_agents: ["codex"],
  is_active: false,
  internal_default: false,
  transcribe_default: false,
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

/** Pick an option in one of the form's shadcn Selects by its labelled trigger. */
function pickOption(label: RegExp, optionName: string) {
  fireEvent.click(screen.getByLabelText(label));
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}

const save = () => fireEvent.click(screen.getByRole("button", { name: /save/i }));

function fillAndSave() {
  fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "conn" } });
  fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: "sk-x" } });
  save();
}

describe("ProviderForm no longer writes compatible_agents", () => {
  test("the create body carries no compatible_agents", async () => {
    const onSubmit = renderCreate();
    fillAndSave();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const body = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(body).not.toHaveProperty("compatible_agents");
    // The fields that DO belong to a connection still travel.
    expect(body).toMatchObject({ name: "conn", protocol: "openai", secret_value: "sk-x" });
  });

  test("the create body carries no compatible_agents for a keyless wire either", async () => {
    const onSubmit = renderCreate();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "local" } });
    pickOption(/vendor/i, "Ollama");
    save();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const body = onSubmit.mock.calls[0][0] as Record<string, unknown>;
    expect(body).not.toHaveProperty("compatible_agents");
    expect(body).toMatchObject({ protocol: "ollama" });
  });

  test("the patch body carries no compatible_agents", async () => {
    const onUpdate = renderEdit();
    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: "https://gw2/v1" } });
    save();
    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
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

describe("ProviderForm edits the wire, and only when it moved", () => {
  // The `Props` comment on `initial` used to say "protocol locked", which the
  // component's own comment and its edit-mode picker both contradicted. The
  // wire IS editable — a probe that guessed wrong is corrected in place rather
  // than by re-entering the connection, key and all.
  //
  // Whether `protocol` travels in the PATCH is now load-bearing rather than a
  // nicety: the daemon refuses a wire CHANGE on a connection that is switched
  // on (409 PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE), because the wire decides
  // which agents a connection covers and which `use-builtin` reverts. Sending
  // the unchanged wire back would turn every "save the endpoint" on a live
  // connection into that refusal.
  test("a changed wire travels in the patch", async () => {
    const onUpdate = renderEdit();
    pickOption(/protocol/i, "Anthropic");
    save();
    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    const patch = onUpdate.mock.calls[0][0] as Record<string, unknown>;
    expect(patch).toMatchObject({ protocol: "anthropic" });
  });

  test("an unchanged wire does not travel, so editing a live connection is not refused", async () => {
    const onUpdate = renderEdit();
    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: "https://gw2/v1" } });
    save();
    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    const patch = onUpdate.mock.calls[0][0] as Record<string, unknown>;
    expect(patch).not.toHaveProperty("protocol");
    expect(patch).toMatchObject({ base_url: "https://gw2/v1" });
  });
});

describe("ProviderForm validation", () => {
  test("a blank name and a bare hostname are refused under their fields, and nothing is sent", async () => {
    const onSubmit = renderCreate();
    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "api.openai.com/v1" },
    });
    fireEvent.change(screen.getByLabelText(/api key/i), { target: { value: "sk-x" } });
    save();

    expect(await screen.findByText("Enter a name")).toBeInTheDocument();
    expect(screen.getByText(/enter a full url/i)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  test("the key is required on create for a keyed wire, optional on edit", async () => {
    const onSubmit = renderCreate();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "conn" } });
    save();
    expect(await screen.findByText("Enter the API key")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  test("the protocol picker shows display labels, never the raw enum value", () => {
    renderEdit();
    // The stored wire is `openai`; the trigger says what that is.
    expect(screen.getByLabelText(/protocol/i)).toHaveTextContent("OpenAI-compatible");
    expect(screen.queryByText(/^openai$/)).not.toBeInTheDocument();
    // Editing keeps the stored key unless a new one is typed.
    expect(screen.getByLabelText(/api key/i)).toHaveAttribute(
      "placeholder",
      "Leave blank to keep the current value",
    );
  });
});
