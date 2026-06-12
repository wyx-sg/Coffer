// frontend/src/pages/settings/SecuritySettings.test.tsx
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SecuritySettings } from "./SecuritySettings";

vi.mock("@/lib/hooks/useCredentialSettings", () => ({
  useCredentialSettings: vi.fn(),
  useUpdateCredentialSettings: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useCredentialSettings");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const mutate = vi.fn();

afterEach(() => vi.clearAllMocks());

function seed(storage: "file" | "keychain" = "file", mutationError: Error | null = null) {
  vi.mocked(hooks.useCredentialSettings).mockReturnValue({
    data: { master_key_storage: storage },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useCredentialSettings>);
  vi.mocked(hooks.useUpdateCredentialSettings).mockReturnValue({
    mutate,
    isPending: false,
    isError: mutationError !== null,
    error: mutationError,
  } as unknown as ReturnType<typeof hooks.useUpdateCredentialSettings>);
}

describe("SecuritySettings", () => {
  test("renders file state: switch unchecked and fileNote visible", () => {
    seed("file");
    render(<SecuritySettings />, { wrapper: wrap });

    const toggle = screen.getByRole("switch");
    expect(toggle).not.toBeChecked();
    expect(
      screen.getByText("Master key: file beside the database (no keychain prompts)."),
    ).toBeInTheDocument();
  });

  test("toggling on calls mutate with master_key_storage: keychain and shows keychainNote", async () => {
    seed("file");
    render(<SecuritySettings />, { wrapper: wrap });

    fireEvent.click(screen.getByRole("switch"));

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith({ master_key_storage: "keychain" }),
    );
  });

  test("renders keychain state: switch checked and keychainNote visible", () => {
    seed("keychain");
    render(<SecuritySettings />, { wrapper: wrap });

    const toggle = screen.getByRole("switch");
    expect(toggle).toBeChecked();
    expect(
      screen.getByText("Master key: OS keychain (may prompt once per daemon start)."),
    ).toBeInTheDocument();
  });

  test("mutation error shows role=alert", () => {
    const err = new Error("update credential settings failed");
    seed("file", err);
    render(<SecuritySettings />, { wrapper: wrap });

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
