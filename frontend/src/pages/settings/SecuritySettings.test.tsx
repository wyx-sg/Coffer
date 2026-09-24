// frontend/src/pages/settings/SecuritySettings.test.tsx
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { SecuritySettings } from "./SecuritySettings";

vi.mock("@/lib/hooks/useCredentialSettings", () => ({
  useCredentialSettings: vi.fn(),
  useUpdateCredentialSettings: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useCredentialSettings");

// Whether `vault_sync` is on decides whether the Sync link is there at all.
const syncOn = vi.fn((): boolean | undefined => true);
vi.mock("@/lib/hooks/useFeatures", () => ({
  useFeatureEnabled: () => syncOn(),
}));

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const mutate = vi.fn();

afterEach(() => {
  vi.clearAllMocks();
  syncOn.mockReturnValue(true);
});

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

  test("toggling on asks first, then moves the key to the keychain", async () => {
    seed("file");
    render(<SecuritySettings />, { wrapper: wrap });

    fireEvent.click(screen.getByRole("switch"));
    // Nothing is written until the consequence has been read and confirmed.
    expect(mutate).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/move the master key to the os keychain\?/i);
    expect(dialog).toHaveTextContent(/each daemon start/i);

    fireEvent.click(screen.getByRole("button", { name: /move key/i }));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith({ master_key_storage: "keychain" }));
  });

  test("toggling off asks about the file direction, and cancel writes nothing", async () => {
    seed("keychain");
    render(<SecuritySettings />, { wrapper: wrap });

    fireEvent.click(screen.getByRole("switch"));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/move the master key to a file beside the database\?/i);

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mutate).not.toHaveBeenCalled();
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

  test("links to the Sync page for carrying the key to another machine", () => {
    seed("file");
    render(<SecuritySettings />, { wrapper: wrap });
    expect(screen.getByRole("link", { name: /export or import the key/i })).toHaveAttribute(
      "href",
      "/sync",
    );
  });

  test("leaves out the Sync link while vault sync is switched off", () => {
    syncOn.mockReturnValue(false);
    seed("file");
    render(<SecuritySettings />, { wrapper: wrap });
    expect(screen.queryByRole("link", { name: /export or import the key/i })).toBeNull();
  });

  test("mutation error shows role=alert", () => {
    const err = new Error("update credential settings failed");
    seed("file", err);
    render(<SecuritySettings />, { wrapper: wrap });

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
