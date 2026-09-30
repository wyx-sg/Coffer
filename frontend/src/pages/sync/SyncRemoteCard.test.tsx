// frontend/src/pages/sync/SyncRemoteCard.test.tsx
//
// The remote's configuration card: an explicit form behind one Save button
// (disabled until the draft is changed and valid), a pause switch that flips
// the stored remote and only works once one exists, "Check repository" asked
// of the draft, "Stop syncing" behind a confirmation, the vault's path with
// the cloud-folder warning — and the invariant that nothing on it can hold a
// secret: the push credential is named by REFERENCE.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import type { SyncStatus } from "@/lib/api/sync";
import { SyncRemoteCard } from "./SyncRemoteCard";
import { idleMutation, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({
  useSaveSyncRemote: vi.fn(),
  useCheckRemote: vi.fn(),
  useClearSyncRemote: vi.fn(),
}));

const { useSaveSyncRemote, useCheckRemote, useClearSyncRemote } =
  await import("@/lib/hooks/useSync");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

let saveMutate: ReturnType<typeof vi.fn>;
let checkMutate: ReturnType<typeof vi.fn>;
let clearMutate: ReturnType<typeof vi.fn>;

beforeEach(() => {
  saveMutate = vi.fn();
  checkMutate = vi.fn();
  clearMutate = vi.fn();
  mocked(useSaveSyncRemote).mockReturnValue(idleMutation({ mutate: saveMutate }));
  mocked(useCheckRemote).mockReturnValue(idleMutation({ mutate: checkMutate, data: undefined }));
  mocked(useClearSyncRemote).mockReturnValue(idleMutation({ mutate: clearMutate }));
});
afterEach(() => vi.clearAllMocks());

function status(configured: boolean, over: Partial<SyncStatus> = {}): SyncStatus {
  const base = makeStatus({
    areas: { knowledge_documents: 0, skills: 0, resources: 0, secrets: 7, secrets_synced: false },
    ...over,
  });
  return configured ? base : { ...base, configured: false, remote: null, joined: false };
}

const saveButton = () => screen.getByRole("button", { name: /save remote/i });

describe("SyncRemoteCard", () => {
  test("renders the stored remote and the vault's path", () => {
    render(<SyncRemoteCard status={status(true)} />);
    expect(screen.getByLabelText(/repository url/i)).toHaveValue(
      "https://git.example.com/me/vault.git",
    );
    expect(screen.getByLabelText(/push credential/i)).toHaveValue("sync.PUSH_TOKEN");
    expect(screen.getByText("/Users/me/.coffer/vault")).toBeInTheDocument();
    expect(screen.queryByTestId("sync-cloud-folder")).not.toBeInTheDocument();
  });

  test("a vault inside a cloud-synced folder is warned about, with the tool and path", () => {
    render(<SyncRemoteCard status={status(true, { synchroniser: "iCloud Drive" })} />);
    const warning = screen.getByTestId("sync-cloud-folder");
    expect(warning).toHaveTextContent("iCloud Drive");
    expect(warning).toHaveTextContent("/Users/me/.coffer/vault");
  });

  test("Save is disabled until a field changes, then saves the whole remote", () => {
    render(<SyncRemoteCard status={status(true)} />);
    expect(saveButton()).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/branch/i), { target: { value: "vault" } });
    fireEvent.click(saveButton());
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ branch: "vault", enabled: true, include_secret: false }),
      expect.anything(),
    );
  });

  test("the secrets switch says how many would be pushed, and saves include_secret", () => {
    render(<SyncRemoteCard status={status(true)} />);
    expect(screen.getByText(/7 encrypted secrets/i)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/include encrypted secrets/i));
    fireEvent.click(saveButton());
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ include_secret: true }),
      expect.anything(),
    );
    expect(saveMutate.mock.calls[0][0]).not.toHaveProperty("worktree_path");
  });

  test("a URL that is not a git remote blocks Save and says why", () => {
    render(<SyncRemoteCard status={status(false)} />);
    const url = screen.getByLabelText(/repository url/i);
    fireEvent.change(url, { target: { value: "not a url" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/git remote url/i);
    expect(saveButton()).toBeDisabled();
    fireEvent.change(url, { target: { value: "git@github.com:me/vault.git" } });
    expect(saveButton()).toBeEnabled();
  });

  test("the pause switch saves at once, from the STORED remote, and is inert until one exists", () => {
    const { rerender } = render(<SyncRemoteCard status={status(false)} />);
    expect(screen.getByRole("switch", { name: /sync automatically/i })).toBeDisabled();

    rerender(<SyncRemoteCard status={status(true)} />);
    fireEvent.change(screen.getByLabelText(/branch/i), { target: { value: "draft" } });
    fireEvent.click(screen.getByRole("switch", { name: /sync automatically/i }));
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false, branch: "main" }),
      expect.anything(),
    );
  });

  test("Check repository asks about the draft and shows the answer", () => {
    const { rerender } = render(<SyncRemoteCard status={status(true)} />);
    fireEvent.click(screen.getByRole("button", { name: /check repository/i }));
    expect(checkMutate).toHaveBeenCalledWith({
      url: "https://git.example.com/me/vault.git",
      branch: "main",
      credential_ref: "sync.PUSH_TOKEN",
    });

    mocked(useCheckRemote).mockReturnValue(
      idleMutation({
        data: { result: "auth_failed", tip: null, layout: null, detail: "HTTP 403" },
      }),
    );
    rerender(<SyncRemoteCard status={status(true)} />);
    expect(screen.getByTestId("sync-remote-check")).toHaveTextContent(/refused/i);
    expect(screen.getByTestId("sync-remote-check")).toHaveTextContent("HTTP 403");
  });

  test("Stop syncing asks first, then forgets the remote", () => {
    render(<SyncRemoteCard status={status(true)} />);
    fireEvent.click(screen.getByRole("button", { name: /stop syncing/i }));
    expect(clearMutate).not.toHaveBeenCalled();
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: /stop syncing/i }),
    );
    expect(clearMutate).toHaveBeenCalled();
  });

  test("Stop syncing is not offered before there is a remote", () => {
    render(<SyncRemoteCard status={status(false)} />);
    expect(screen.queryByRole("button", { name: /stop syncing/i })).not.toBeInTheDocument();
  });

  acceptance("vault-sync", "the push credential never reaches the repository", () => {
    // What the daemon serves is a ref and nothing secret-shaped...
    const served = status(true).remote as unknown as Record<string, unknown>;
    expect(served.credential_ref).toBe("sync.PUSH_TOKEN");
    const secretish = /token|password|credential(?!_ref)/i;
    expect(Object.keys(served).filter((k) => secretish.test(k))).toEqual([]);

    // ...and what the card renders is that ref, never a password field.
    render(<SyncRemoteCard status={status(true)} />);
    expect(screen.getByLabelText(/push credential/i)).toHaveValue("sync.PUSH_TOKEN");
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0);
  });
});
