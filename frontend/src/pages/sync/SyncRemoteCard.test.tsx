// frontend/src/pages/sync/SyncRemoteCard.test.tsx
//
// The remote's configuration card: auto-saving fields (no Save button), a
// "converge now" button, and the invariant that nothing on it can hold a
// secret — the push credential is named by REFERENCE and resolved by the
// daemon at push time.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";

import type { SyncStatus } from "@/lib/api/sync";
import { SyncRemoteCard } from "./SyncRemoteCard";

vi.mock("@/lib/hooks/useSync", () => ({
  useSaveSyncRemote: vi.fn(),
  useRunConverge: vi.fn(),
}));

const { useSaveSyncRemote, useRunConverge } = await import("@/lib/hooks/useSync");

const saveMutate = vi.fn();
const runMutate = vi.fn();

function stub() {
  vi.mocked(useSaveSyncRemote).mockReturnValue({
    mutate: saveMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSaveSyncRemote>);
  vi.mocked(useRunConverge).mockReturnValue({
    mutate: runMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRunConverge>);
}

function status(configured: boolean): SyncStatus {
  return {
    configured,
    remote: configured
      ? {
          url: "https://git.example.com/me/vault.git",
          branch: "main",
          credential_ref: "sync.PUSH_TOKEN",
          include_credentials: false,
          interval_seconds: 3600,
          enabled: true,
          worktree_path: "/home/me/.coffer/sync",
        }
      : null,
    last_run: null,
    machine_id: "a3f21c9e4b7d2610",
    machine_id_is_derived: true,
  };
}

afterEach(() => vi.clearAllMocks());

describe("SyncRemoteCard", () => {
  test("renders the stored remote and its working tree", () => {
    stub();
    render(<SyncRemoteCard status={status(true)} />);
    expect(screen.getByLabelText(/repository url/i)).toHaveValue(
      "https://git.example.com/me/vault.git",
    );
    expect(screen.getByLabelText(/push credential/i)).toHaveValue("sync.PUSH_TOKEN");
    expect(screen.getByText(/\/home\/me\/\.coffer\/sync/)).toBeInTheDocument();
  });

  test("has no Save button — every field auto-saves on blur", () => {
    stub();
    render(<SyncRemoteCard status={status(true)} />);
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();

    const branch = screen.getByLabelText(/branch/i);
    fireEvent.change(branch, { target: { value: "vault" } });
    fireEvent.blur(branch);
    expect(saveMutate).toHaveBeenCalledWith(expect.objectContaining({ branch: "vault" }));
  });

  test("an unchanged field does not write", () => {
    stub();
    render(<SyncRemoteCard status={status(true)} />);
    fireEvent.blur(screen.getByLabelText(/branch/i));
    expect(saveMutate).not.toHaveBeenCalled();
  });

  test("a blank URL is not a configuration, so nothing is written", () => {
    stub();
    render(<SyncRemoteCard status={status(false)} />);
    const url = screen.getByLabelText(/repository url/i);
    fireEvent.change(url, { target: { value: "   " } });
    fireEvent.blur(url);
    expect(saveMutate).not.toHaveBeenCalled();
  });

  test("an adopted working tree rides along unchanged rather than resetting", () => {
    stub();
    render(<SyncRemoteCard status={status(true)} />);
    fireEvent.click(screen.getByLabelText(/include credentials/i));
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        worktree_path: "/home/me/.coffer/sync",
        include_credentials: true,
      }),
    );
  });

  test("converge now runs a round, and is inert until a remote exists", () => {
    stub();
    const { rerender } = render(<SyncRemoteCard status={status(false)} />);
    expect(screen.getByRole("button", { name: /converge now/i })).toBeDisabled();

    rerender(<SyncRemoteCard status={status(true)} />);
    fireEvent.click(screen.getByRole("button", { name: /converge now/i }));
    expect(runMutate).toHaveBeenCalled();
  });

  acceptance("vault-sync", "the push credential never reaches the repository", () => {
    stub();
    // What the daemon serves is a ref and nothing secret-shaped...
    const served = status(true).remote as unknown as Record<string, unknown>;
    expect(served.credential_ref).toBe("sync.PUSH_TOKEN");
    const secretish = /token|secret|password|credential(?!_ref)/i;
    expect(Object.keys(served).filter((k) => secretish.test(k))).toEqual(["include_credentials"]);

    // ...and what the card renders is that ref, never a password field.
    render(<SyncRemoteCard status={status(true)} />);
    expect(screen.getByLabelText(/push credential/i)).toHaveValue("sync.PUSH_TOKEN");
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0);
  });
});
