// frontend/src/pages/settings/SecuritySettings.test.tsx
//
// Settings › Security against a fake daemon: only `fetch` is replaced, and the
// fake accepts a request only when it carries the token the daemon currently
// holds — so "the next request succeeds with the new token" is something the
// test can actually observe rather than assume.
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { getApiClient, resetApiClient, unwrap } from "@/lib/api/client";
import { getCofferToken } from "@/lib/auth";
import { acceptance } from "@/test/acceptance";
import { SecuritySettings } from "./SecuritySettings";

// Tested in SecretBoundaryCard.test.tsx; here it would only add two routes.
vi.mock("./SecretBoundaryCard", () => ({
  SecretBoundaryCard: () => <div data-testid="secret-boundary-card" />,
}));
let inApp = false;
const exportBackup = vi.fn();
const backupClosed = vi.fn();
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => inApp,
  exportMasterKeyBackup: (passphrase: string) => exportBackup(passphrase),
  importMasterKey: (material: string, passphrase: string | null) =>
    importKeyInShell(material, passphrase),
}));
vi.mock("@/lib/masterKeyBackup", () => ({
  masterKeyBackupClosed: () => backupClosed(),
}));
const importKeyInShell = vi.fn();

const OLD = "old-token-value-abcd";
const NEW = "new-token-value-9f3a";

type Storage = "file" | "keychain" | "keychain_access_group";
let daemonToken = OLD;
let storage: Storage = "file";
let daemonUp = true;
let rotateFails = false;
let moveFails = false;
const seen: { method: string; path: string; token: string | null }[] = [];
const bodies: Record<string, unknown>[] = [];

// This Mac's key and the one in the other Mac's backup (12 hex, as the daemon
// answers them).
const OWN_FP = "7f3a91c25d0e";
const OTHER_FP = "c04b7719ae62";
const BACKUP = '{"coffer_master_key_backup": 1, "fingerprint": "c04b7719ae62"}';
let currentFp = OWN_FP;

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

async function fakeDaemon(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const req = input instanceof Request ? input : new Request(String(input), init);
  const path = new URL(req.url).pathname.replace(/^\/api\/v1/, "");
  const token = req.headers.get("X-Coffer-Token");
  seen.push({ method: req.method, path, token });
  if (!daemonUp) return json(502, { error: { code: "INTERNAL_ERROR", message: "down" } });
  if (token !== daemonToken) return json(401, { error: { code: "UNAUTHORIZED", message: "bad" } });
  const route = `${req.method} ${path}`;
  if (route === "GET /daemon/status") return json(200, { version: "1.0.0" });
  if (route === "GET /settings/secrets") return json(200, { master_key_storage: storage });
  if (route === "PUT /settings/secrets") {
    if (moveFails)
      return json(503, { error: { code: "MASTER_KEY_MISSING", message: "keychain refused" } });
    storage = ((await req.json()) as { master_key_storage: Storage }).master_key_storage;
    return json(200, { master_key_storage: storage });
  }
  if (route === "GET /secrets/key/fingerprint") return json(200, { fingerprint: currentFp });
  if (route === "POST /secrets/key/import/preview") {
    const body = (await req.json()) as { material: string };
    const fp = body.material === BACKUP ? OTHER_FP : OWN_FP;
    return json(200, {
      fingerprint: fp,
      current_fingerprint: currentFp,
      same: fp === currentFp,
      protected: body.material === BACKUP,
    });
  }
  if (route === "POST /daemon/rotate-token") {
    if (rotateFails)
      return json(503, {
        error: { code: "INTERNAL_ERROR", message: "could not write daemon.json" },
      });
    daemonToken = NEW;
    return json(200, { token: NEW });
  }
  return json(404, { error: { code: "NOT_FOUND", message: route } });
}

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  daemonToken = OLD;
  storage = "file";
  daemonUp = true;
  rotateFails = false;
  moveFails = false;
  inApp = false;
  seen.length = 0;
  bodies.length = 0;
  currentFp = OWN_FP;
  (window as unknown as { __COFFER_TOKEN__?: string }).__COFFER_TOKEN__ = OLD;
  resetApiClient();
  vi.stubGlobal("fetch", vi.fn(fakeDaemon));
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  const w = window as unknown as { __COFFER_TOKEN__?: string; __COFFER_BASE_URL__?: string };
  delete w.__COFFER_TOKEN__;
  delete w.__COFFER_BASE_URL__;
  resetApiClient();
});

const renderPage = () => render(<SecuritySettings />, { wrapper: wrap });
const tokenBox = () => screen.getByTestId("daemon-token");
const rotateButton = () => screen.getByRole("button", { name: /^rotate…$/i });

describe("SecuritySettings — master key", () => {
  test("a signed build's access-group key reads OK and has nothing to move", async () => {
    storage = "keychain_access_group";
    renderPage();
    expect(await screen.findByText("Keychain")).toBeInTheDocument();
    expect(screen.queryByText(/development build/i)).not.toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.getByTestId("secret-boundary-card")).toBeInTheDocument();
  });

  test("a development build says plainly that the key is a readable file", async () => {
    renderPage();
    const toggle = await screen.findByRole("switch");
    expect(toggle).not.toBeChecked();
    expect(screen.getByText("Key file")).toBeInTheDocument();
    expect(screen.getByText(/a file any process of yours can read/i)).toBeInTheDocument();
    expect(
      screen.getByText("Master key: file beside the database (no keychain prompts)."),
    ).toBeInTheDocument();
  });

  test("toggling on asks first, then moves the key to the keychain and closes", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("switch"));
    // Nothing is written until the consequence has been read and confirmed.
    expect(seen.some((r) => r.method === "PUT")).toBe(false);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/move the master key to the os keychain\?/i);
    expect(dialog).toHaveTextContent(/each daemon start/i);

    fireEvent.click(within(dialog).getByRole("button", { name: /move key/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(storage).toBe("keychain");
  });

  test("toggling off asks about the file direction, and cancel writes nothing", async () => {
    storage = "keychain";
    renderPage();
    const toggle = await screen.findByRole("switch");
    expect(toggle).toBeChecked();
    expect(
      screen.getByText("Master key: OS keychain (may prompt once per daemon start)."),
    ).toBeInTheDocument();

    fireEvent.click(toggle);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/move the master key to a file beside the database\?/i);
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(seen.some((r) => r.method === "PUT")).toBe(false);
  });

  test("a refused move keeps the confirmation open with the reason", async () => {
    moveFails = true;
    renderPage();
    fireEvent.click(await screen.findByRole("switch"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /move key/i }));

    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(storage).toBe("file");
  });

  test("the key fingerprint reads in groups of four", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("key-fingerprint")).toHaveTextContent("7F3A 91C2 5D0E"),
    );
  });

  acceptance("secret", "the browser offers no master key export", async () => {
    renderPage();
    const button = await screen.findByRole("button", { name: "Open in Coffer app to export" });
    expect(button).toBeDisabled();
    expect(screen.getByText(/only available in the coffer desktop app/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /export master key/i })).toBeNull();
    expect(exportBackup).not.toHaveBeenCalled();
  });

  test("in the desktop app the export asks for a passphrase twice, then says where the file went", async () => {
    inApp = true;
    exportBackup.mockResolvedValue({
      path: "/Users/me/Documents/coffer-master-key.cfk",
      fingerprint: OWN_FP,
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /export master key/i }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Export the master key");
    const submit = within(dialog).getByRole("button", { name: "Export key…" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Protect the file with a passphrase"), {
      target: { value: "correct horse" },
    });
    fireEvent.change(within(dialog).getByLabelText("Repeat passphrase"), {
      target: { value: "correct hors" },
    });
    expect(dialog).toHaveTextContent("The passphrases don't match.");
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Repeat passphrase"), {
      target: { value: "correct horse" },
    });
    fireEvent.click(submit);

    await waitFor(() => expect(dialog).toHaveTextContent("Master key exported"));
    expect(exportBackup).toHaveBeenCalledWith("correct horse");
    expect(dialog).toHaveTextContent(
      "Saved coffer-master-key.cfk to ~/Documents · recorded in Activity.",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: /done/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Closing tells the shell, so a command waiting on this dialog stops waiting.
    expect(backupClosed).toHaveBeenCalled();
  });

  test("a cancelled presence check leaves the export dialog open without an error", async () => {
    inApp = true;
    exportBackup.mockRejectedValue("cancelled");
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /export master key/i }));
    const dialog = await screen.findByRole("dialog");
    for (const label of ["Protect the file with a passphrase", "Repeat passphrase"])
      fireEvent.change(within(dialog).getByLabelText(label), { target: { value: "long enough" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Export key…" }));

    await waitFor(() => expect(exportBackup).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toHaveTextContent("Export the master key");
    expect(within(dialog).queryByRole("alert")).toBeNull();
  });

  test("a browser offers no key import, only the way to the app", async () => {
    renderPage();
    const button = await screen.findByTestId("master-key-import-open-in-app");
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Open the Coffer app to import a master key");
    expect(screen.queryByRole("button", { name: "Import…" })).toBeNull();
  });

  test("a cancelled presence check leaves the import dialog open without an error", async () => {
    inApp = true;
    importKeyInShell.mockRejectedValue("cancelled");
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Import…" }));
    const dialog = await screen.findByRole("dialog");
    const file = Object.assign(new File([BACKUP], "k.cfk"), { text: async () => BACKUP });
    fireEvent.change(within(dialog).getByLabelText("Key file"), { target: { files: [file] } });
    await waitFor(() => expect(within(dialog).getByTestId("key-in-file")).toBeInTheDocument());
    fireEvent.change(within(dialog).getByLabelText("Passphrase"), { target: { value: "pw" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Replace key" }));
    await waitFor(() => expect(importKeyInShell).toHaveBeenCalledWith(BACKUP, "pw"));
    expect(within(dialog).queryByRole("alert")).toBeNull();
  });

  acceptance("secret", "the security tab replaces a key and names what stays locked", async () => {
    inApp = true;
    // The shell does the presence check and the daemon call; the page only
    // hands it the file's text and the passphrase.
    importKeyInShell.mockImplementation(async (material: string, passphrase: string | null) => {
      bodies.push({ material, passphrase });
      if (passphrase !== "correct horse") throw "the passphrase does not open this key file";
      currentFp = OTHER_FP;
      return {
        fingerprint: OTHER_FP,
        replaced: true,
        readable: 6,
        locked_refs: ["secret/linear-api-key", "secret/jira-pat-2024"],
      };
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Import…" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Replace this Mac’s master key?");
    const replace = within(dialog).getByRole("button", { name: "Replace key" });
    expect(replace).toBeDisabled();

    // jsdom's File has no text(); the page reads the picked file with it.
    const file = Object.assign(
      new File([BACKUP], "coffer-master-key.cfk", { type: "application/json" }),
      { text: async () => BACKUP },
    );
    fireEvent.change(within(dialog).getByLabelText("Key file"), { target: { files: [file] } });

    await waitFor(() =>
      expect(within(dialog).getByTestId("key-in-file")).toHaveTextContent(
        "C04B 7719 AE62 · different",
      ),
    );
    expect(within(dialog).getByTestId("key-file-name")).toHaveTextContent("coffer-master-key.cfk");
    expect(dialog).toHaveTextContent("7F3A 91C2 5D0E");
    expect(dialog).toHaveTextContent("Recorded in Activity");
    // Nothing is replaced by choosing the file.
    expect(bodies).toHaveLength(0);
    expect(replace).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("Passphrase"), {
      target: { value: "wrong one" },
    });
    fireEvent.click(replace);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "the passphrase does not open this key file",
    );

    fireEvent.change(within(dialog).getByLabelText("Passphrase"), {
      target: { value: "correct horse" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Replace key" }));

    await waitFor(() => expect(screen.getByRole("dialog")).toHaveTextContent("Key imported"));
    const done = screen.getByRole("dialog");
    expect(done).toHaveTextContent(
      "This Mac now uses key C04B 7719 AE62, but 2 secrets still can’t be decrypted with it.",
    );
    expect(within(done).getByTestId("readable-now")).toHaveTextContent("6 secrets");
    expect(within(done).getByTestId("still-locked")).toHaveTextContent(
      "linear-api-key, jira-pat-2024",
    );
    expect(within(done).getByRole("button", { name: "Open Secrets" })).toBeInTheDocument();
    expect(bodies.at(-1)).toEqual({ material: BACKUP, passphrase: "correct horse" });
    // The fingerprint row follows the key this Mac now uses.
    fireEvent.click(within(done).getByRole("button", { name: /done/i }));
    await waitFor(() =>
      expect(screen.getByTestId("key-fingerprint")).toHaveTextContent("C04B 7719 AE62"),
    );
  });
});

describe("SecuritySettings — daemon access token", () => {
  acceptance("web-ui", "the token is hidden until shown", async () => {
    renderPage();
    await waitFor(() => expect(rotateButton()).toBeEnabled());
    expect(tokenBox()).toHaveTextContent(/^•+abcd$/);
    expect(tokenBox()).not.toHaveTextContent(OLD);

    fireEvent.click(screen.getByRole("button", { name: /^show$/i }));
    expect(tokenBox()).toHaveTextContent(OLD);
    fireEvent.click(screen.getByRole("button", { name: /^hide$/i }));
    expect(tokenBox()).not.toHaveTextContent(OLD);

    fireEvent.click(screen.getByRole("button", { name: /^copy$/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(OLD));
  });

  acceptance(
    "web-ui",
    "rotating the token from settings security keeps the page working",
    async () => {
      renderPage();
      await waitFor(() => expect(rotateButton()).toBeEnabled());
      fireEvent.click(rotateButton());
      const dialog = await screen.findByRole("dialog");
      expect(dialog).toHaveTextContent(/other open coffer tabs and any client/i);
      expect(dialog).toHaveTextContent("~/.coffer/daemon.json");
      expect(dialog).toHaveTextContent(/token_rotated/);

      fireEvent.click(within(dialog).getByRole("button", { name: /rotate token/i }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

      expect(seen.filter((r) => r.path === "/daemon/rotate-token")).toHaveLength(1);
      expect(getCofferToken()).toBe(NEW);
      expect(tokenBox()).toHaveTextContent(/9f3a$/);
      // No reload: the page's next request carries the new token and is accepted.
      await expect(unwrap(getApiClient().GET("/settings/secrets"))).resolves.toEqual({
        master_key_storage: "file",
      });
      expect(seen.at(-1)?.token).toBe(NEW);
    },
  );

  acceptance("web-ui", "a failed rotation from settings security keeps the old token", async () => {
    rotateFails = true;
    renderPage();
    await waitFor(() => expect(rotateButton()).toBeEnabled());
    fireEvent.click(rotateButton());
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /rotate token/i }));

    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(getCofferToken()).toBe(OLD);
    await expect(unwrap(getApiClient().GET("/settings/secrets"))).resolves.toEqual({
      master_key_storage: "file",
    });
    expect(seen.at(-1)?.token).toBe(OLD);
  });

  test("while the daemon cannot be reached, the token controls are disabled", async () => {
    daemonUp = false;
    renderPage();
    await waitFor(() => expect(rotateButton()).toBeDisabled());
    expect(screen.getByRole("button", { name: /^show$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^copy$/i })).toBeDisabled();
  });

  acceptance("web-ui", "the security tab keeps only machine-level settings", async () => {
    renderPage();
    // Where the master key lives, with its move control (the storage switch).
    await screen.findByRole("switch");
    expect(screen.getByText("Daemon access token")).toBeInTheDocument();
    for (const name of [/^show$/i, /^copy$/i, /^rotate/i]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: /add|reveal|delete/i })).toBeNull();
    // The way to them is a link to the Secrets page.
    expect(screen.getByRole("button", { name: /manage in secrets/i })).toBeInTheDocument();
    // It reads no stored secret: only this machine's key, under /secrets/key.
    const secretReads = seen.filter((r) => r.path.startsWith("/secrets"));
    expect(secretReads.every((r) => r.path.startsWith("/secrets/key/"))).toBe(true);
  });
});
