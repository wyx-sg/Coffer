// src/components/secret/ReplaceSecretDialog.test.tsx — the one Replace dialog:
// a new value goes into the current secret; another stored secret is handed to onRebind;
// without onRebind only a new value is offered; a secret missing here reads Add.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { secretsApi } from "@/lib/api/secret";
import { acceptance } from "@/test/acceptance";
import { ReplaceSecretDialog } from "./ReplaceSecretDialog";

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

function wrap(onRebind?: (ref: string) => Promise<unknown>, ref = CURRENT) {
  const onClose = vi.fn();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <MemoryRouter>
          <ReplaceSecretDialog
            secretRef={ref}
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

describe("ReplaceSecretDialog", () => {
  test("a new value is written into the secret the field uses now", async () => {
    const onRebind = vi.fn();
    const onClose = wrap(onRebind);
    expect(await screen.findByRole("link", { name: "Old key" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("New value"), { target: { value: "s3cret" } });
    expect(screen.getByRole("heading", { name: "Replace API_KEY" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Replace key" }));
    await waitFor(() => expect(secretsApi.set).toHaveBeenCalledWith(CURRENT, "s3cret"));
    expect(onRebind).not.toHaveBeenCalled();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  acceptance(
    "web-ui",
    "replacing a secret offers a new value or another stored secret",
    async () => {
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
    },
  );

  test("without onRebind only a new value is offered", async () => {
    wrap(undefined);
    expect(await screen.findByLabelText("New value")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use another secret" })).toBeNull();
  });

  acceptance("web-ui", "a secret missing on this Mac reads Add", async () => {
    wrap(undefined, "secret/cccccccccccccccccccccccccccccccc");
    expect(await screen.findByRole("heading", { name: "Add API_KEY" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("New value"), { target: { value: "v" } });
    fireEvent.click(screen.getByRole("button", { name: "Add key" }));
    await waitFor(() =>
      expect(secretsApi.set).toHaveBeenCalledWith("secret/cccccccccccccccccccccccccccccccc", "v"),
    );
  });
});
