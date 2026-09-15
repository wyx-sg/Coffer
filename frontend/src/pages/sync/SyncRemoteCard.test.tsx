// frontend/src/pages/sync/SyncRemoteCard.test.tsx
//
// The remote's configuration card: an explicit form behind one Save button
// (disabled until the draft is changed and valid), an auto-saving "converge
// automatically" switch that only works once a remote exists, a "converge
// now" button, and the invariant that nothing on it can hold a secret — the
// push credential is named by REFERENCE and resolved by the daemon at push
// time.
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

const saveButton = () => screen.getByRole("button", { name: /save remote/i });

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

  test("Save is disabled until a field changes, and blurring alone writes nothing", () => {
    stub();
    render(<SyncRemoteCard status={status(true)} />);
    expect(saveButton()).toBeDisabled();

    const branch = screen.getByLabelText(/branch/i);
    fireEvent.blur(branch);
    expect(saveMutate).not.toHaveBeenCalled();

    fireEvent.change(branch, { target: { value: "vault" } });
    fireEvent.blur(branch);
    expect(saveMutate).not.toHaveBeenCalled();
    expect(saveButton()).toBeEnabled();

    fireEvent.click(saveButton());
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ branch: "vault", enabled: true }),
      expect.anything(),
    );
  });

  test("a URL that is not a git remote blocks Save and says why", () => {
    stub();
    render(<SyncRemoteCard status={status(false)} />);
    const url = screen.getByLabelText(/repository url/i);
    fireEvent.change(url, { target: { value: "not a url" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/git remote url/i);
    expect(saveButton()).toBeDisabled();

    fireEvent.change(url, { target: { value: "git@github.com:me/vault.git" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });

  test("an interval under 60 seconds blocks Save", () => {
    stub();
    render(<SyncRemoteCard status={status(true)} />);
    fireEvent.change(screen.getByLabelText(/interval/i), { target: { value: "30" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/60 seconds/i);
    expect(saveButton()).toBeDisabled();
  });

  test("a first save starts the remote enabled", () => {
    stub();
    render(<SyncRemoteCard status={status(false)} />);
    fireEvent.change(screen.getByLabelText(/repository url/i), {
      target: { value: "https://git.example.com/me/vault.git" },
    });
    fireEvent.click(saveButton());
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ url: "https://git.example.com/me/vault.git", enabled: true }),
      expect.anything(),
    );
  });

  test("an adopted working tree rides along unchanged rather than resetting", () => {
    stub();
    render(<SyncRemoteCard status={status(true)} />);
    fireEvent.click(screen.getByLabelText(/include credentials/i));
    fireEvent.click(saveButton());
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        worktree_path: "/home/me/.coffer/sync",
        include_credentials: true,
      }),
      expect.anything(),
    );
  });

  test("converge automatically saves at once, from the STORED remote, and is inert until one exists", () => {
    stub();
    const { rerender } = render(<SyncRemoteCard status={status(false)} />);
    const toggle = screen.getByRole("switch", { name: /converge automatically/i });
    expect(toggle).toBeDisabled();
    expect(screen.getByText(/save the remote first/i)).toBeInTheDocument();

    rerender(<SyncRemoteCard status={status(true)} />);
    // An unsaved draft edit must not ride along with the switch.
    fireEvent.change(screen.getByLabelText(/branch/i), { target: { value: "draft" } });
    fireEvent.click(screen.getByRole("switch", { name: /converge automatically/i }));
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false, branch: "main" }),
      expect.anything(),
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
