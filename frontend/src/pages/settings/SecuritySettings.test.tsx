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

import { call } from "@/lib/api/call";
import { resetApiClient } from "@/lib/api/client";
import { getCofferToken } from "@/lib/auth";
import { SecuritySettings } from "./SecuritySettings";

// Tested in SecretBoundaryCard.test.tsx; here it would only add two routes.
vi.mock("./SecretBoundaryCard", () => ({
  SecretBoundaryCard: () => <div data-testid="secret-boundary-card" />,
}));
let inApp = false;
const exportBackup = vi.fn();
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => inApp,
  exportMasterKeyBackup: () => exportBackup(),
}));

const OLD = "old-token-value-abcd";
const NEW = "new-token-value-9f3a";

type Storage = "file" | "keychain" | "keychain_access_group";
let daemonToken = OLD;
let storage: Storage = "file";
let daemonUp = true;
let rotateFails = false;
let moveFails = false;
const seen: { method: string; path: string; token: string | null }[] = [];

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
  if (route === "GET /settings/credentials") return json(200, { master_key_storage: storage });
  if (route === "PUT /settings/credentials") {
    if (moveFails)
      return json(503, { error: { code: "MASTER_KEY_MISSING", message: "keychain refused" } });
    storage = ((await req.json()) as { master_key_storage: Storage }).master_key_storage;
    return json(200, { master_key_storage: storage });
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
    expect(await screen.findByText(/only coffer's signed apps can read it/i)).toBeInTheDocument();
    expect(screen.getByText("Keychain")).toBeInTheDocument();
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

  test("in a browser the export names the desktop app instead of offering a control", async () => {
    renderPage();
    expect(await screen.findByText("Open in Coffer app")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /export master key/i })).toBeNull();
  });

  test("in the desktop app the export reports where the file went", async () => {
    inApp = true;
    exportBackup.mockResolvedValue({
      path: "/Users/me/Documents/coffer-master-key.cfk",
      fingerprint: "3f9a11",
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /export master key/i }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Master key exported");
    expect(dialog).toHaveTextContent(
      "Saved coffer-master-key.cfk to /Users/me/Documents · recorded in Activity.",
    );
    expect(dialog).toHaveTextContent("3f9a11");
    fireEvent.click(within(dialog).getByRole("button", { name: /done/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("SecuritySettings — daemon access token", () => {
  // Scenario (revise-web-ui-ia): "the token is hidden until shown"
  test("the token is masked until Show, and Copy puts it on the clipboard", async () => {
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

  // Scenario (revise-web-ui-ia): "rotating the token from settings security keeps the page working"
  test("rotating installs the new token, closes, and the next request succeeds", async () => {
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
    await expect(call("/settings/credentials")).resolves.toEqual({ master_key_storage: "file" });
    expect(seen.at(-1)?.token).toBe(NEW);
  });

  // Scenario (revise-web-ui-ia): "a failed rotation from settings security keeps the old token"
  test("a failed rotation keeps the dialog open with the error and the old token", async () => {
    rotateFails = true;
    renderPage();
    await waitFor(() => expect(rotateButton()).toBeEnabled());
    fireEvent.click(rotateButton());
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /rotate token/i }));

    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(getCofferToken()).toBe(OLD);
    await expect(call("/settings/credentials")).resolves.toEqual({ master_key_storage: "file" });
    expect(seen.at(-1)?.token).toBe(OLD);
  });

  test("while the daemon cannot be reached, the token controls are disabled", async () => {
    daemonUp = false;
    renderPage();
    await waitFor(() => expect(rotateButton()).toBeDisabled());
    expect(screen.getByRole("button", { name: /^show$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^copy$/i })).toBeDisabled();
  });

  // Scenario (revise-web-ui-ia): "the security tab keeps only machine-level settings"
  test("the tab lists no stored secret and offers no add, reveal or delete", async () => {
    renderPage();
    await screen.findByRole("switch");
    expect(screen.getByText("Daemon access token")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: /add|reveal|delete/i })).toBeNull();
    // The way to them is a link to the Secrets page.
    expect(screen.getByRole("button", { name: /manage in secrets/i })).toBeInTheDocument();
    expect(seen.some((r) => r.path.startsWith("/credentials"))).toBe(false);
  });
});
