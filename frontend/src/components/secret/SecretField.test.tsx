// src/components/secret/SecretField.test.tsx — the shared secret field and the
// header / env rows: choose stored, paste new, New secret…, plain value,
// Missing, and the "Store it in Coffer?" hint. Only `secretsApi` is mocked.
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { SecretRef } from "@/lib/api/secret";
import { persistNewSecrets, type KeyValueSecretRow, type SecretFieldValue } from "./secretValue";
import { KeyValueSecretRows } from "./KeyValueSecretRows";
import { SecretField } from "./SecretField";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: { list: vi.fn(), set: vi.fn(), pendingApprovals: vi.fn() },
}));
const { secretsApi } = await import("@/lib/api/secret");
const api = vi.mocked(secretsApi);

const stored = (name: string, uses = 0): SecretRef =>
  ({
    ref: `secret/${name}`,
    present: true,
    locked: false,
    bindings: [],
    cited_by: Array.from({ length: uses }, (_, i) => ({
      kind: "mcp_server",
      uid: `u${i}`,
      name: `srv${i}`,
    })),
    mentioned_by_skills: [],
  }) as unknown as SecretRef;

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function FieldHarness({ initial = null }: { initial?: SecretFieldValue }) {
  const [value, setValue] = useState<SecretFieldValue>(initial);
  return (
    <>
      <SecretField
        aria-label="API key"
        value={value}
        onChange={setValue}
        defaultName="openai-key"
      />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </>
  );
}

function RowsHarness({ initial }: { initial: KeyValueSecretRow[] }) {
  const [rows, setRows] = useState(initial);
  return (
    <>
      <KeyValueSecretRows
        rows={rows}
        onChange={setRows}
        label="Headers"
        keyPlaceholder="Authorization"
        addLabel="Add header"
      />
      <output data-testid="rows">{JSON.stringify(rows)}</output>
    </>
  );
}

const current = (id: string) => JSON.parse(screen.getByTestId(id).textContent ?? "null");

beforeEach(() => {
  api.list.mockResolvedValue({ refs: [stored("openai-key", 3), stored("deploy-token", 0)] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
  api.set.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe("SecretField", () => {
  test("choosing a stored secret shows its name, with used-by counts in the menu", async () => {
    wrap(<FieldHarness />);
    fireEvent.click(screen.getByRole("button", { name: /choose a secret for api key/i }));
    const list = await screen.findByRole("listbox");
    expect(await within(list).findByText("used by 3")).toBeInTheDocument();
    fireEvent.click(within(list).getByRole("option", { name: /deploy-token/ }));
    expect(current("value")).toEqual({ kind: "stored", name: "deploy-token" });
    expect(screen.getByText("deploy-token")).toBeInTheDocument();
  });

  test("pasting a value makes a new secret named after the thing, written only on persist", async () => {
    wrap(<FieldHarness />);
    await screen.findByPlaceholderText("Choose a secret, or paste a new value");
    // openai-key is taken, so the default name gets a suffix.
    await waitFor(() => expect(api.list).toHaveBeenCalled());
    await screen.findByRole("button", { name: /choose a secret/i });
    fireEvent.paste(screen.getByPlaceholderText("Choose a secret, or paste a new value"), {
      clipboardData: { getData: () => "sk-abc123" },
    });
    await waitFor(() =>
      expect(current("value")).toEqual({ kind: "new", name: "openai-key-2", value: "sk-abc123" }),
    );
    expect(screen.getByText("New · saved on Add")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-abc123")).not.toBeInTheDocument();
    expect(api.set).not.toHaveBeenCalled();

    await persistNewSecrets([current("value")]);
    expect(api.set).toHaveBeenCalledWith("secret/openai-key-2", "sk-abc123");
  });

  test("New secret… writes to Secrets and selects it", async () => {
    wrap(<FieldHarness />);
    fireEvent.click(screen.getByRole("button", { name: /choose a secret for api key/i }));
    fireEvent.click(await screen.findByRole("button", { name: "New secret…" }));
    const dialog = await screen.findByRole("dialog", { name: "New secret" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "grafana-token" } });
    fireEvent.change(within(dialog).getByLabelText("Value"), { target: { value: "glsa_1" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add secret" }));
    await waitFor(() => expect(api.set).toHaveBeenCalledWith("secret/grafana-token", "glsa_1"));
    await waitFor(() =>
      expect(current("value")).toEqual({ kind: "stored", name: "grafana-token" }),
    );
  });

  test("a chosen secret this machine does not hold is Missing", async () => {
    wrap(<FieldHarness initial={{ kind: "stored", name: "gone" }} />);
    expect(await screen.findByText("Missing")).toBeInTheDocument();
  });
});

describe("KeyValueSecretRows", () => {
  const plain = (key: string, value: string): KeyValueSecretRow => ({
    key,
    value: { kind: "plain", value },
  });

  test("value is plain text; the key button picks a secret, Type a plain value goes back", async () => {
    wrap(<RowsHarness initial={[plain("Authorization", "")]} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose a secret for Authorization" }));
    fireEvent.click(await screen.findByRole("option", { name: /deploy-token/ }));
    expect(current("rows")).toEqual([
      { key: "Authorization", value: { kind: "stored", name: "deploy-token" } },
    ]);
    fireEvent.click(screen.getByRole("button", { name: /Authorization: secret deploy-token/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Type a plain value" }));
    expect(current("rows")).toEqual([plain("Authorization", "")]);
  });

  test("Add header appends a plain row; delete removes it", () => {
    wrap(<RowsHarness initial={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /add header/i }));
    expect(current("rows")).toEqual([plain("", "")]);
    fireEvent.click(screen.getByRole("button", { name: "Remove Headers" }));
    expect(current("rows")).toEqual([]);
  });

  test("a secret-looking plain value gets the Store it in Coffer? hint", () => {
    wrap(<RowsHarness initial={[plain("X-Api-Token", "abc")]} />);
    fireEvent.click(screen.getByRole("button", { name: "Store it in Coffer?" }));
    expect(current("rows")).toEqual([
      { key: "X-Api-Token", value: { kind: "new", name: "x-api-token", value: "abc" } },
    ]);
  });

  test("a plain value that is not secret-like has no hint", () => {
    wrap(<RowsHarness initial={[plain("Accept", "application/json")]} />);
    expect(screen.queryByText("This looks like a secret.")).not.toBeInTheDocument();
  });

  test("a missing referenced secret shows the warning", async () => {
    wrap(
      <RowsHarness initial={[{ key: "Authorization", value: { kind: "stored", name: "gone" } }]} />,
    );
    expect(await screen.findByText("Missing")).toBeInTheDocument();
  });
});
