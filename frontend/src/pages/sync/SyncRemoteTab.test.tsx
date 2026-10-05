// frontend/src/pages/sync/SyncRemoteTab.test.tsx
//
// Sync › Remote (6.4.27/28/29): settings that save themselves — a text field
// on blur, a picker or switch at once — always as the whole stored remote
// with one field changed; the Secret is a pick from the store (a reference,
// never a value); "Only when I press Sync now" is how a remote pauses; turning
// secrets on asks first; Stop syncing runs at once and its toast offers Undo.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render as rtlRender, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import type { SyncRemote, SyncStatus } from "@/lib/api/sync";
import { SyncRemoteTab } from "./SyncRemoteTab";
import { idleMutation, makeStatus } from "./syncTestKit";
import type { FormState } from "./syncRemoteForm";

/** The secret field's dialogs read the query cache. */
const render = (ui: React.ReactElement) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (node: React.ReactElement) => (
    <QueryClientProvider client={qc}>{node}</QueryClientProvider>
  );
  const out = rtlRender(wrap(ui));
  return { ...out, rerender: (next: React.ReactElement) => out.rerender(wrap(next)) };
};

vi.mock("@/lib/hooks/useSync", () => ({
  useSaveSyncRemote: vi.fn(),
  useClearSyncRemote: vi.fn(),
  useRestoreSyncRemote: vi.fn(),
  useMoveVault: vi.fn(),
}));
const toast = { info: vi.fn(), error: vi.fn(), success: vi.fn() };
vi.mock("@/components/ui/toast", () => ({ useToast: () => ({ toast }) }));
/** Writing a pasted token to Secrets, as the store would: the form comes back citing it. */
const storePushToken = vi.fn(async (form: FormState) =>
  form.secret?.kind === "new"
    ? { ...form, secret: { kind: "stored" as const, name: form.secret.name } }
    : form,
);
vi.mock("./useStorePushToken", () => ({ useStorePushToken: () => storePushToken }));
vi.mock("@/lib/hooks/useSecrets", async (original) => ({
  ...(await original<object>()),
  useSecrets: vi.fn(),
}));

const { useSaveSyncRemote, useClearSyncRemote, useRestoreSyncRemote, useMoveVault } =
  await import("@/lib/hooks/useSync");
const { useSecrets } = await import("@/lib/hooks/useSecrets");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

let save: ReturnType<typeof vi.fn>;
let clear: ReturnType<typeof vi.fn>;
let restore: ReturnType<typeof vi.fn>;
const DEPLOY_KEY = `secret/${"a1".repeat(16)}`;
const GITLAB_TOKEN = `secret/${"b2".repeat(16)}`;
const ref = (id: string, label: string) => ({
  ref: id,
  label,
  present: true,
  cited_by: [],
  bindings: [],
  mentioned_by_skills: [],
  uri: null,
});

beforeEach(() => {
  save = vi.fn();
  clear = vi.fn((_: unknown, opts?: { onSuccess?: (r: { restorable: boolean }) => void }) =>
    opts?.onSuccess?.({ restorable: true }),
  );
  restore = vi.fn();
  mocked(useSaveSyncRemote).mockReturnValue(idleMutation({ mutate: save }));
  mocked(useClearSyncRemote).mockReturnValue(idleMutation({ mutate: clear }));
  mocked(useRestoreSyncRemote).mockReturnValue(idleMutation({ mutate: restore }));
  mocked(useMoveVault).mockReturnValue(idleMutation({ mutate: vi.fn() }));
  mocked(useSecrets).mockReturnValue({
    data: { refs: [ref(DEPLOY_KEY, "github-deploy-key"), ref(GITLAB_TOKEN, "gitlab-token")] },
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
      secret_ref: DEPLOY_KEY,
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
      secret_ref: DEPLOY_KEY,
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
    expect(sent()).toMatchObject({ secret_ref: GITLAB_TOKEN });
  });

  acceptance(
    "web-ui",
    "a secret field at the window's edge opens its menu inside the window",
    () => {
      const { container } = renderTab();
      fireEvent.click(screen.getByLabelText("Secret"));
      const menu = screen.getByRole("listbox").closest<HTMLElement>("[role=dialog]")!;
      // The shared secret menu: portalled out of the row and placed by the popper, which keeps it
      // inside the window's edges, not hung off the field where the row puts it.
      expect(container.contains(menu)).toBe(false);
      expect(menu.closest("[data-radix-popper-content-wrapper]")).not.toBeNull();
      expect(within(menu).getByRole("button", { name: "New secret…" })).toBeInTheDocument();
      fireEvent.click(within(menu).getByRole("button", { name: "None" }));
      expect(sent()).toMatchObject({ secret_ref: null });
    },
  );

  acceptance("web-ui", "a pasted push token is stored when the remote saves", async () => {
    renderTab(status({ secret_ref: null }));
    fireEvent.paste(screen.getByLabelText("Secret"), {
      clipboardData: { getData: () => "glpat-token" },
    });
    await waitFor(() => expect(sent()?.secret_ref).toMatch(/^secret\/[0-9a-f]{32}$/));
    expect(storePushToken).toHaveBeenCalledWith(
      expect.objectContaining({
        secret: expect.objectContaining({ kind: "new", value: "glpat-token" }),
      }),
    );
    expect(screen.queryByText("glpat-token")).not.toBeInTheDocument();
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

  test("Stop syncing runs at once, and the toast's Undo puts the remote back", () => {
    renderTab();
    fireEvent.click(screen.getByRole("button", { name: "Stop syncing" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(clear).toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalledWith("Stopped syncing this Mac", {
      undo: expect.any(Function),
    });
    toast.info.mock.calls[0][1].undo();
    expect(restore).toHaveBeenCalled();
  });

  test("a vault in a cloud-synced folder can be moved from here", () => {
    renderTab(status({}, { synchroniser: "iCloud Drive" }));
    expect(screen.getByRole("button", { name: "Move the vault…" })).toBeInTheDocument();
  });
});
