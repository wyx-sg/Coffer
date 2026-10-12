// src/components/providers/EditProviderDialog.test.tsx — the Edit dialog replaces the key in place:
// Replace opens the same fields as the Replace key dialog, and Save sends the key after the rest.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { providersApi, type Provider } from "@/lib/api/providers";
import { acceptance } from "@/test/acceptance";
import { EditProviderDialog } from "./EditProviderDialog";

const KEY = "secret/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const OTHER = "secret/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

vi.mock("@/lib/api/providers", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/providers")>()),
  providersApi: { update: vi.fn(async () => ({})) },
}));

vi.mock("@/lib/api/secret", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/secret")>()),
  secretsApi: {
    list: vi.fn(async () => ({
      refs: [KEY, OTHER].map((ref, i) => ({
        ref,
        label: i === 0 ? "Agnes API Key" : "Team key",
        present: true,
        cited_by: [],
        mentioned_by_skills: [],
        bindings: [],
      })),
    })),
  },
}));

const PROVIDER = {
  uid: "p1",
  name: "Agnes",
  protocol: "openai",
  base_url: "https://apihub.example.com/v1",
  anthropic_base_url: null,
  secret_ref: KEY,
} as unknown as Provider;

function show() {
  const onClose = vi.fn();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <MemoryRouter>
          <EditProviderDialog
            open
            provider={PROVIDER}
            use={{ agents: [], transcribe: null }}
            onClose={onClose}
            onSaved={() => undefined}
          />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return onClose;
}

afterEach(() => vi.clearAllMocks());

describe("EditProviderDialog key", () => {
  test("Save without Replace leaves the key alone", async () => {
    const onClose = show();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(providersApi.update).not.toHaveBeenCalled();
  });

  acceptance("web-ui", "a provider's Edit dialog replaces its key with the form", async () => {
    const onClose = show();
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    fireEvent.change(screen.getByLabelText(/^New value/), { target: { value: "sk-new" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(providersApi.update).toHaveBeenCalledWith("p1", { secret_value: "sk-new" }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  test("another stored secret re-points the provider", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    fireEvent.click(screen.getByRole("button", { name: "Use another secret" }));
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: /Team key/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(providersApi.update).toHaveBeenCalledWith("p1", { secret_ref: OTHER }),
    );
  });

  test("Keep current key folds the fields away and sends nothing", async () => {
    const onClose = show();
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    fireEvent.change(screen.getByLabelText(/^New value/), { target: { value: "sk-new" } });
    fireEvent.click(screen.getByRole("button", { name: "Keep current key" }));
    expect(screen.queryByLabelText(/^New value/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(providersApi.update).not.toHaveBeenCalled();
  });
});
