// frontend/src/pages/settings/SyncBackupCard.test.tsx
//
// The backup card (spec vault-export-import `## Backup`). Unlike its sibling
// card tests this one drives the real useSync hooks against a stubbed `fetch`,
// because what matters here is the wire: which request each edit sends, and —
// for the acceptance scenario — what is and is not in those payloads.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { acceptance } from "@/test/acceptance";
import type { BackupRemote, BackupRemoteState, BackupRun, BackupStatus } from "@/lib/hooks/useSync";
import { SyncBackupCard } from "./SyncBackupCard";

const CONFIGURED: BackupRemote = {
  url: "https://git.example.invalid/me/vault.git",
  branch: "backup",
  // A NAME in the credential store. The daemon resolves it at push time; the
  // secret itself has no field on this wire at all.
  credential_ref: "sync.BACKUP_TOKEN",
  include_credentials: true,
  interval_seconds: 900,
  enabled: true,
  worktree_path: "~/.coffer/sync",
};

interface Recorded {
  method: string;
  path: string;
  body: Record<string, unknown> | undefined;
}

let calls: Recorded[];
let remoteState: BackupRemoteState;
let lastRun: BackupRun | null;

/** A tiny stand-in for the four backup routes, recording everything it is sent. */
function installFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname.replace("/api/v1", "");
      const method = init?.method ?? "GET";
      const body = init?.body
        ? (JSON.parse(String(init.body)) as Record<string, unknown>)
        : undefined;
      calls.push({ method, path, body });

      const json = (payload: unknown) =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "content-type": "application/json" },
        });

      if (method === "GET" && path === "/sync/remote") return json(remoteState);
      if (method === "GET" && path === "/sync/status") {
        return json({
          configured: remoteState.configured,
          remote: remoteState.remote,
          last_run: lastRun,
        } satisfies BackupStatus);
      }
      if (method === "PUT" && path === "/sync/remote") {
        // The daemon stores what it was given and echoes it back, so the card
        // re-syncs to the value it just saved rather than to a stale one.
        const stored = { worktree_path: "~/.coffer/sync", ...body } as unknown as BackupRemote;
        remoteState = { configured: true, remote: stored };
        return json(stored);
      }
      if (method === "POST" && path === "/sync/push") {
        lastRun = { status: "ok", commit: "abc1234", error: null, ran_at: "2026-09-12T03:00:00Z" };
        return json(lastRun);
      }
      return new Response("not found", { status: 404 });
    }),
  );
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SyncBackupCard />
    </QueryClientProvider>,
  );
}

/** Wait until the daemon's answer has landed in the form. */
async function renderConfigured() {
  renderCard();
  await screen.findByDisplayValue(CONFIGURED.url);
}

const requests = (method: string, path: string) =>
  calls.filter((c) => c.method === method && c.path === path);

beforeEach(() => {
  calls = [];
  remoteState = { configured: true, remote: { ...CONFIGURED } };
  lastRun = null;
  installFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("SyncBackupCard", () => {
  test("renders the configured remote the daemon reports", async () => {
    await renderConfigured();
    expect(screen.getByLabelText(/repository url/i)).toHaveValue(CONFIGURED.url);
    expect(screen.getByLabelText(/branch/i)).toHaveValue("backup");
    expect(screen.getByLabelText(/every \(seconds\)/i)).toHaveValue(900);
    expect(screen.getByLabelText(/back up automatically/i)).toBeChecked();
    expect(screen.getByLabelText(/include credentials/i)).toBeChecked();
  });

  test("auto-saves (no Save button) — the URL persists on blur", async () => {
    await renderConfigured();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();

    const url = screen.getByLabelText(/repository url/i);
    fireEvent.change(url, { target: { value: "https://git.example.invalid/me/other.git" } });
    fireEvent.blur(url);

    await waitFor(() => expect(requests("PUT", "/sync/remote")).toHaveLength(1));
    expect(requests("PUT", "/sync/remote")[0].body).toMatchObject({
      url: "https://git.example.invalid/me/other.git",
      branch: "backup",
      credential_ref: "sync.BACKUP_TOKEN",
      include_credentials: true,
      interval_seconds: 900,
      enabled: true,
      // The adopted working tree rides along rather than being reset to the
      // default by a card that does not even offer the field.
      worktree_path: "~/.coffer/sync",
    });
  });

  test("a blurred field that did not change sends nothing", async () => {
    await renderConfigured();
    fireEvent.blur(screen.getByLabelText(/repository url/i));
    await waitFor(() => expect(requests("GET", "/sync/remote")).not.toHaveLength(0));
    expect(requests("PUT", "/sync/remote")).toHaveLength(0);
  });

  test("the enable switch persists the moment it moves", async () => {
    await renderConfigured();
    fireEvent.click(screen.getByLabelText(/back up automatically/i));

    await waitFor(() => expect(requests("PUT", "/sync/remote")).toHaveLength(1));
    expect(requests("PUT", "/sync/remote")[0].body).toMatchObject({ enabled: false });
  });

  test("the credentials opt-in persists on the remote, not per run", async () => {
    await renderConfigured();
    fireEvent.click(screen.getByLabelText(/include credentials/i));

    await waitFor(() => expect(requests("PUT", "/sync/remote")).toHaveLength(1));
    expect(requests("PUT", "/sync/remote")[0].body).toMatchObject({ include_credentials: false });
  });

  test("an interval edit is clamped to a positive number of seconds", async () => {
    await renderConfigured();
    const interval = screen.getByLabelText(/every \(seconds\)/i);
    fireEvent.change(interval, { target: { value: "0" } });
    expect(interval).toHaveValue(1);
    fireEvent.blur(interval);

    await waitFor(() => expect(requests("PUT", "/sync/remote")).toHaveLength(1));
    expect(requests("PUT", "/sync/remote")[0].body).toMatchObject({ interval_seconds: 1 });
  });

  test("an unconfigured vault saves nothing until a URL is typed", async () => {
    remoteState = { configured: false, remote: null };
    renderCard();
    await waitFor(() => expect(requests("GET", "/sync/remote")).toHaveLength(1));

    const url = screen.getByLabelText(/repository url/i);
    expect(url).toHaveValue("");
    // The spec's defaults are what an empty card opens on.
    expect(screen.getByLabelText(/branch/i)).toHaveValue("main");
    expect(screen.getByLabelText(/every \(seconds\)/i)).toHaveValue(3600);

    fireEvent.blur(url);
    fireEvent.click(screen.getByLabelText(/include credentials/i));
    await waitFor(() => expect(screen.getByLabelText(/include credentials/i)).toBeChecked());
    expect(requests("PUT", "/sync/remote")).toHaveLength(0);
    // Nothing to push to, either.
    expect(screen.getByRole("button", { name: /back up now/i })).toBeDisabled();
  });

  test("'Back up now' pushes and refreshes the status", async () => {
    await renderConfigured();
    expect(screen.getByTestId("backup-last-run")).toHaveTextContent(/no backup has run yet/i);

    fireEvent.click(screen.getByRole("button", { name: /back up now/i }));

    await waitFor(() => expect(requests("POST", "/sync/push")).toHaveLength(1));
    await waitFor(() => expect(screen.getByTestId("backup-last-run")).toHaveTextContent(/pushed/i));
    expect(screen.getByTestId("backup-last-run")).toHaveTextContent("abc1234");
    // The refresh is a real refetch, not a locally patched cache.
    expect(requests("GET", "/sync/status").length).toBeGreaterThan(1);
  });

  test("a failed run shows its reason without killing the card", async () => {
    lastRun = {
      status: "push_failed",
      commit: "def5678",
      error: "fatal: could not read Password for 'https://***@host'",
      ran_at: "2026-09-12T02:00:00Z",
    };
    await renderConfigured();

    const run = await screen.findByTestId("backup-last-run");
    await waitFor(() => expect(run).toHaveTextContent(/push failed/i));
    expect(run).toHaveTextContent("def5678");
    expect(screen.getByRole("alert")).toHaveTextContent("could not read Password");
  });
});

// The backend half of this scenario — that the token never lands in the
// repository's git config — is pinned by test_the_token_never_lands_in_git_config.
// This is the surface half: what the daemon hands a browser, and what the
// browser hands back, carry a credential *reference* and nothing else.
acceptance("vault-export-import", "the push credential never reaches the repository", async () => {
  await renderConfigured();

  // 1. What GET /sync/remote served: a ref, and no secret-shaped field.
  const served = remoteState.remote as unknown as Record<string, unknown>;
  expect(served.credential_ref).toBe("sync.BACKUP_TOKEN");
  const secretish = /token|secret|password|credential(?!_ref)/i;
  expect(Object.keys(served).filter((k) => secretish.test(k))).toEqual(["include_credentials"]);

  // 2. What the card shows: the ref itself, and no password field anywhere.
  expect(screen.getByLabelText(/push credential/i)).toHaveValue("sync.BACKUP_TOKEN");
  expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0);

  // 3. What the card sends back — including on a push, which is the run that
  //    actually authenticates: still only the ref, never a value to redact.
  fireEvent.click(screen.getByLabelText(/include credentials/i));
  // The card refuses to back up while a config save is still in flight, so a
  // run would otherwise use the configuration it is in the middle of
  // replacing. Let the save land before asking for the push.
  await waitFor(() => expect(requests("PUT", "/sync/remote")).toHaveLength(1));
  fireEvent.click(screen.getByRole("button", { name: /back up now/i }));
  await waitFor(() => expect(requests("POST", "/sync/push")).toHaveLength(1));

  for (const call of calls) {
    const sent = Object.keys(call.body ?? {});
    expect(sent.filter((k) => secretish.test(k)).sort()).toEqual(
      sent.includes("credential_ref") ? ["include_credentials"] : [],
    );
    expect(JSON.stringify(call.body ?? {})).not.toContain("sync.BACKUP_TOKEN_VALUE");
  }
});
