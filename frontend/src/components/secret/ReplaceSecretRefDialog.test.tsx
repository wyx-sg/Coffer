// src/components/secret/ReplaceSecretRefDialog.test.tsx — replace a field's secret in place:
// a new value goes into the current secret; another stored secret is handed to onRebind.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { secretsApi } from "@/lib/api/secret";
import { ReplaceSecretRefDialog } from "./ReplaceSecretRefDialog";

const CURRENT = "secret/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const OTHER = "secret/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

vi.mock("@/lib/api/secret", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/secret")>()),
  secretsApi: {
    set: vi.fn(async () => undefined),
    list: vi.fn(async () => ({
      refs: [
        {
          ref: CURRENT,
          label: "Old key",
          present: true,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
        {
          ref: OTHER,
          label: "Team key",
          present: true,
          cited_by: [],
          mentioned_by_skills: [],
          bindings: [],
        },
      ],
    })),
  },
}));

function wrap(onRebind: (ref: string) => Promise<unknown>) {
  const onClose = vi.fn();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <MemoryRouter>
          <ReplaceSecretRefDialog
            secretRef={CURRENT}
            field="API_KEY"
            onClose={onClose}
            onRebind={onRebind}
          />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return onClose;
}

describe("ReplaceSecretRefDialog", () => {
  test("a new value is written into the secret the field uses now", async () => {
    const onRebind = vi.fn();
    const onClose = wrap(onRebind);
    expect(await screen.findByRole("link", { name: "Old key" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("New value"), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: "Replace value" }));
    await waitFor(() => expect(secretsApi.set).toHaveBeenCalledWith(CURRENT, "s3cret"));
    expect(onRebind).not.toHaveBeenCalled();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  test("another stored secret is offered (not the current one) and handed to onRebind", async () => {
    const onRebind = vi.fn(async () => undefined);
    const onClose = wrap(onRebind);
    fireEvent.click(screen.getByRole("button", { name: "Use another secret" }));
    fireEvent.click(screen.getByRole("combobox"));
    expect(await screen.findByRole("option", { name: /Team key/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Old key/ })).toBeNull();
    fireEvent.click(screen.getByRole("option", { name: /Team key/ }));
    fireEvent.click(screen.getByRole("button", { name: "Use this secret" }));
    await waitFor(() => expect(onRebind).toHaveBeenCalledWith(OTHER));
    expect(secretsApi.set).not.toHaveBeenCalledWith(OTHER, expect.anything());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
