// frontend/src/pages/sync/SyncRemoteTab.test.tsx
//
// Sync › Remote (6.5.22/23/26): settings that save themselves — a text field
// on blur, a picker or switch at once — always as the whole stored remote
// with one field changed; the Secret is a pick from the store (a reference,
// never a value); "Only when I press Sync now" is how a remote pauses; turning
// secrets on asks first; Stop syncing asks and names what it forgets.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import type { SyncRemote, SyncStatus } from "@/lib/api/sync";
import { SyncRemoteTab } from "./SyncRemoteTab";
import { idleMutation, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ useSaveSyncRemote: vi.fn(), useClearSyncRemote: vi.fn() }));
vi.mock("@/lib/hooks/useSecrets", () => ({ useSecrets: vi.fn() }));

const { useSaveSyncRemote, useClearSyncRemote } = await import("@/lib/hooks/useSync");
const { useSecrets } = await import("@/lib/hooks/useSecrets");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

let save: ReturnType<typeof vi.fn>;
let clear: ReturnType<typeof vi.fn>;
const ref = (name: string) => ({ ref: `secret/${name}`, present: true, cited_by: [], uri: null });

beforeEach(() => {
  save = vi.fn();
  clear = vi.fn();
  mocked(useSaveSyncRemote).mockReturnValue(idleMutation({ mutate: save }));
  mocked(useClearSyncRemote).mockReturnValue(idleMutation({ mutate: clear }));
  mocked(useSecrets).mockReturnValue({
    data: { refs: [ref("github-deploy-key"), ref("gitlab-token")] },
  });
});
afterEach(() => vi.clearAllMocks());

function status(remote: Partial<SyncRemote> = {}, over: Partial<SyncStatus> = {}): SyncStatus {
  const s = makeStatus(over);
  return {
    ...s,
    areas: { ...s.areas, secrets: 8 },
    remote: {
      ...s.remote!,
      secret_ref: "secret/github-deploy-key",
      interval_seconds: 3600,
      ...remote,
    },
  };
}

function renderTab(s: SyncStatus = status(), path = "/sync?tab=remote") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SyncRemoteTab status={s} />
    </MemoryRouter>,
  );
}

const sent = () => save.mock.calls.at(-1)?.[0];
const pick = (name: RegExp | string) => fireEvent.click(screen.getByRole("option", { name }));

describe("SyncRemoteTab", () => {
  test("shows the stored remote, the chosen secret by name, and where the vault is", () => {
    renderTab();
    expect(screen.getByLabelText("Repository URL")).toHaveValue(
      "https://git.example.com/me/vault.git",
    );
    expect(screen.getByLabelText("Branch")).toHaveValue("main");
    expect(screen.getByLabelText("Secret")).toHaveTextContent("github-deploy-key");
    expect(screen.getByText("/Users/me/.coffer/vault")).toBeInTheDocument();
    expect(screen.queryByTestId("sync-cloud-folder")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });

  test("a text field saves the whole remote on blur, and only when it changed", () => {
    renderTab();
    const branch = screen.getByLabelText("Branch");
    fireEvent.blur(branch);
    expect(save).not.toHaveBeenCalled();
    fireEvent.change(branch, { target: { value: "vault" } });
    fireEvent.blur(branch);
    expect(sent()).toEqual({
      url: "https://git.example.com/me/vault.git",
      branch: "vault",
      secret_ref: "secret/github-deploy-key",
      username: "coffer",
      include_secret: false,
      interval_seconds: 3600,
      enabled: true,
    });
  });

  test("a URL that is not a git remote says why and is not sent", () => {
    renderTab();
    const url = screen.getByLabelText("Repository URL");
    fireEvent.change(url, { target: { value: "not a url" } });
    fireEvent.blur(url);
    expect(screen.getByRole("alert")).toHaveTextContent(/git remote url/i);
    expect(save).not.toHaveBeenCalled();
  });

  test("picking a secret saves at once", () => {
    renderTab();
    fireEvent.click(screen.getByLabelText("Secret"));
    pick(/gitlab-token/);
    expect(sent()).toMatchObject({ secret_ref: "secret/gitlab-token" });
  });

  test("?focus=secret opens the secret picker", () => {
    renderTab(status(), "/sync?tab=remote&focus=secret");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  acceptance("vault-sync", "the push secret never reaches the repository", () => {
    // What the daemon serves is a ref and nothing secret-shaped...
    const served = status().remote as unknown as Record<string, unknown>;
    const secretish = /token|password|secret(?!_ref)/i;
    expect(Object.keys(served).filter((k) => secretish.test(k))).toEqual(["include_secret"]);
    // ...and the tab renders that ref as a pick, never a value field.
    renderTab();
    expect(screen.getByLabelText("Secret")).toHaveTextContent("github-deploy-key");
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0);
  });

  acceptance("vault-sync", "a token is sent with the username the remote names", () => {
    const { unmount } = renderTab(status({ username: "coffer" }));
    const user = screen.getByLabelText("User name");
    expect(user).toHaveValue("");
    fireEvent.change(user, { target: { value: "oauth2" } });
    fireEvent.blur(user);
    expect(sent()).toMatchObject({ username: "oauth2" });
    unmount();

    // An SSH remote has no user-name field, and keeps the stored one unchanged.
    save.mockClear();
    renderTab(status({ url: "git@github.com:me/vault.git", username: "stored-name" }));
    expect(screen.queryByLabelText("User name")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "vault" } });
    fireEvent.blur(screen.getByLabelText("Branch"));
    expect(sent()).toMatchObject({ username: "stored-name", branch: "vault" });
  });

  test("Only when I press Sync now pauses the remote; a cadence resumes it", () => {
    renderTab();
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Run a round" }), { key: "ArrowDown" });
    pick("Only when I press Sync now");
    expect(sent()).toMatchObject({ enabled: false, interval_seconds: 3600 });
  });

  test("a paused remote reads as manual, and an unusual interval is its own option", () => {
    renderTab(status({ enabled: false, interval_seconds: 420 }));
    const cadence = screen.getByRole("combobox", { name: "Run a round" });
    expect(cadence).toHaveTextContent("Only when I press Sync now");
    fireEvent.keyDown(cadence, { key: "ArrowDown" });
    pick("Every 7 minutes");
    expect(sent()).toMatchObject({ enabled: true, interval_seconds: 420 });
  });

  test("including secrets asks first, with how many; turning them off does not", () => {
    renderTab();
    fireEvent.click(screen.getByRole("switch", { name: "Include encrypted secrets" }));
    expect(save).not.toHaveBeenCalled();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText(/8 secrets are pushed as ciphertext/)).toBeInTheDocument();
    expect(dialog.getByText(/master key stays on this Mac/)).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Include secrets" }));
    expect(sent()).toMatchObject({ include_secret: true });
  });

  test("a vault inside a cloud-synced folder is warned about, naming the tool", () => {
    renderTab(status({}, { synchroniser: "iCloud Drive" }));
    expect(screen.getByTestId("sync-cloud-folder")).toHaveTextContent("iCloud Drive");
  });

  test("Stop syncing asks first, naming the remote, then forgets it", () => {
    renderTab();
    fireEvent.click(screen.getByRole("button", { name: "Stop syncing…" }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("https://git.example.com/me/vault.git")).toBeInTheDocument();
    expect(clear).not.toHaveBeenCalled();
    fireEvent.click(dialog.getByRole("button", { name: "Stop syncing" }));
    expect(clear).toHaveBeenCalled();
  });
});
