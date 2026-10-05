// src/pages/SecretsPage.test.tsx — the Secrets page: the list with what uses each secret, add, delete refused while in use, reveal only in the desktop app, secrets missing on this Mac, and changes waiting for approval.
//
// Only the network boundary (`secretsApi`) and the desktop shell's seam
// (`@/lib/tauri`) are mocked; the query client, router and i18n are real.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import type { SecretRef } from "@/lib/api/secret";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { ApiError } from "@/lib/api/errors";
import { SecretsPage } from "./SecretsPage";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    list: vi.fn(),
    set: vi.fn(),
    remove: vi.fn(),
    add: vi.fn(),
    setNotes: vi.fn(),
    scan: vi.fn(),
    importFindings: vi.fn(),
    pendingApprovals: vi.fn(),
    secretBoundary: vi.fn(),
    rejectApproval: vi.fn(),
  },
}));
// The attention list the banners' × (Ignore) shares with Overview.
let attention: { items: unknown[]; ignored: unknown[] } = { items: [], ignored: [] };
const ignoreAttention = vi.fn().mockResolvedValue(undefined);
vi.mock("@/lib/api/attention", () => ({
  attentionApi: {
    read: () => Promise.resolve({ ...attention, counts_by_kind: {}, errors: [] }),
    ignore: (key: string) => ignoreAttention(key),
    unignore: vi.fn(),
  },
}));
let inShell = false;
const revealSecret = vi.fn();
vi.mock("@/lib/tauri", () => ({
  presenceAvailable: () => inShell,
  revealSecret: (ref: string) => revealSecret(ref),
  approvePending: vi.fn(),
  onApprovalsEvent: () => () => {},
}));

// Whether the page of a citer's kind exists (its feature is on).
let kindPageOpen = true;
vi.mock("@/lib/hooks/useFeatures", () => ({
  useKindPageOpen: () => () => kindPageOpen,
}));

const { secretsApi } = await import("@/lib/api/secret");
const api = vi.mocked(secretsApi);

function ref(over: Partial<SecretRef> & { ref: string }): SecretRef {
  return {
    bindings: [],
    cited_by: [],
    mentioned_by_skills: [],
    present: true,
    locked: false,
    created_at: "2026-08-12T09:00:00Z",
    last_used_at: null,
    readable_by_local_processes: false,
    unreferenced: false,
    uri: null,
    label: null,
    description: null,
    created_for: null,
    ...over,
  };
}

const GITHUB = ref({
  ref: "mcp_server/u-gh/GITHUB_TOKEN",
  label: "github · GITHUB_TOKEN",
  cited_by: [{ kind: "mcp_server", name: "github", uid: "u-gh", slot: null }],
});
const OPENAI = ref({
  ref: "provider/u-oa/api_key",
  label: "OpenAI · api_key",
  present: false,
  cited_by: [{ kind: "provider", name: "OpenAI", uid: "u-oa", slot: null }],
});
const SEATALK = ref({
  ref: "secret/seatalk-app-secret",
  label: "seatalk-app-secret",
  uri: "coffer://secret/seatalk-app-secret",
  cited_by: [{ kind: "channel", name: "SeaTalk", uid: "u-st", slot: null }],
});
const OLD = ref({
  ref: "secret/old-openai-key",
  label: "old-openai-key",
  uri: "coffer://secret/old-openai-key",
  unreferenced: true,
  readable_by_local_processes: true,
});

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname}</p>;
}

function renderPage(path = "/secrets") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path="/secrets" element={<SecretsPage />} />
              <Route path="/secrets/:id" element={<SecretsPage />} />
              <Route path="*" element={<Where />} />
            </Routes>
            <Where />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const at = (ref: string) => `/secrets/${encodeURIComponent(ref)}`;
const openMenu = (name: string) =>
  fireEvent.click(screen.getByRole("button", { name: `Actions for ${name}` }));
const HEX = "0123456789abcdef0123456789abcdef";

beforeEach(() => {
  inShell = false;
  api.list.mockResolvedValue({ refs: [GITHUB, OPENAI, SEATALK, OLD] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
  attention = { items: [], ignored: [] };
  api.remove.mockResolvedValue(undefined);
  api.set.mockResolvedValue(undefined);
});
afterEach(() => {
  vi.clearAllMocks();
  kindPageOpen = true;
});

describe("SecretsPage", () => {
  acceptance("web-ui", "a secret opens on its own detail page with what uses it", async () => {
    renderPage();
    // The list reads names, not ids; nothing is open until a row is.
    const row = await screen.findByRole("link", { name: /OpenAI · api_key/ });
    expect(screen.getByText("Nothing selected")).toBeInTheDocument();
    fireEvent.click(row);
    expect(screen.getAllByTestId("where")[0]).toHaveTextContent(at("provider/u-oa/api_key"));
    // Overview: the reference, whether this Mac holds it, and Used by with a link.
    expect(await screen.findByText("provider/u-oa/api_key")).toBeInTheDocument();
    expect(screen.getByText("No value on this Mac", { selector: "dd *, dd" })).toBeInTheDocument();
    const usedBy = screen.getByRole("region", { name: "Used by" });
    expect(within(usedBy).getByText("OpenAI")).toBeInTheDocument();
    fireEvent.click(within(usedBy).getByRole("link", { name: /OpenAI/ }));
    expect(screen.getAllByTestId("where")[0]).toHaveTextContent("/model-providers/u-oa");
  });

  acceptance("web-ui", "the secrets page lists each secret with what uses it", async () => {
    renderPage();
    // Both are listed: the server's as present, the provider's as missing here.
    const github = await screen.findByRole("link", { name: /github · GITHUB_TOKEN/ });
    const openai = screen.getByRole("link", { name: /OpenAI · api_key/ });
    expect(github.closest("li")).not.toHaveTextContent("No value on this Mac");
    expect(openai.closest("li")).toHaveTextContent("No value on this Mac");
    // Choosing a row names its citer by kind and name, which opens its page.
    fireEvent.click(github);
    const usedBy = await screen.findByRole("region", { name: "Used by" });
    expect(within(usedBy).getByText("github")).toBeInTheDocument();
    expect(within(usedBy).getByText("MCP server")).toBeInTheDocument();
    fireEvent.click(within(usedBy).getByRole("link", { name: /github/ }));
    expect(screen.getAllByTestId("where")[0]).toHaveTextContent("/mcp-servers/github");
  });

  test("a citer whose feature is off is named without a link to its missing page", async () => {
    kindPageOpen = false;
    renderPage(at("provider/u-oa/api_key"));
    const usedBy = await screen.findByRole("region", { name: "Used by" });
    expect(within(usedBy).getByText("OpenAI")).toBeInTheDocument();
    expect(within(usedBy).queryByRole("link")).toBeNull();
  });

  test("a secret nothing uses is found under Not used", async () => {
    renderPage();
    await screen.findByText("old-openai-key");
    const status = screen.getByRole("combobox", { name: "Status" });
    fireEvent.keyDown(status, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "Not used" }));
    await waitFor(() => expect(screen.getByText("old-openai-key")).toBeInTheDocument());
    expect(screen.queryByText(/GITHUB_TOKEN/)).not.toBeInTheDocument();
  });

  acceptance("secret", "a secret this Mac cannot open is missing on this Mac", async () => {
    const locked = ref({
      ref: "secret/sentry-token",
      uri: "coffer://secret/sentry-token",
      label: "sentry-token",
      locked: true,
      cited_by: [{ kind: "mcp_server", name: "sentry", uid: "u-se", slot: null }],
    });
    api.list.mockResolvedValue({ refs: [GITHUB, OPENAI, locked] });
    renderPage(at("secret/sentry-token"));
    const banner = await screen.findByTestId("secrets-missing-banner");
    expect(banner).toHaveTextContent("2 secrets have no value on this Mac");
    expect(banner).toHaveTextContent("OpenAI and sentry can’t start until they have a value.");
    // Importing the master key replaces this Mac's own; it is not offered here.
    expect(within(banner).queryByRole("link")).toBeNull();
    expect(within(banner).getByRole("button", { name: "Add values" })).toBeInTheDocument();
    // The row says so, and the pane's own action is Add value, with reveal off.
    const list = screen.getByRole("group", { name: "Secrets" });
    expect(within(list).getAllByText("No value on this Mac")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Reveal in the Coffer app" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Add value" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a value for sentry-token" });
    fireEvent.change(within(dialog).getByLabelText("New value"), { target: { value: "sntr" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add value" }));
    expect(await screen.findByText("Added a value for sentry-token")).toBeInTheDocument();
    expect(api.set).toHaveBeenCalledWith("secret/sentry-token", "sntr");
  });

  test("search narrows the list by name", async () => {
    renderPage();
    await screen.findByText("old-openai-key");
    fireEvent.change(screen.getByRole("textbox", { name: "Find a secret" }), {
      target: { value: "seatalk" },
    });
    expect(screen.getByText("seatalk-app-secret")).toBeInTheDocument();
    expect(screen.queryByText("old-openai-key")).not.toBeInTheDocument();
  });

  acceptance("secret", "a secret added on the page gets a minted id and its label", async () => {
    api.add.mockResolvedValue({ ref: `secret/${HEX}`, uri: `coffer://secret/${HEX}` });
    renderPage();
    await screen.findByText("seatalk-app-secret");
    fireEvent.click(screen.getByRole("button", { name: "Add secret" }));
    const dialog = await screen.findByRole("dialog", { name: "Add secret" });
    // No name to type: a label and a value.
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "GitHub token" } });
    fireEvent.change(within(dialog).getByLabelText("Value"), { target: { value: "ghp_x" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add secret" }));
    // Then the dialog offers the minted URI to copy, and waits for Done.
    expect(await within(dialog).findByText(`coffer://secret/${HEX}`)).toBeInTheDocument();
    expect(api.add).toHaveBeenCalledWith("GitHub token", "ghp_x");
    expect(api.set).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("the label and description save in place and leave the reference alone", async () => {
    api.setNotes.mockResolvedValue({ ref: SEATALK.ref, label: "SeaTalk bot", description: null });
    renderPage(at(SEATALK.ref));
    const label = await screen.findByRole("textbox", { name: "Name" });
    fireEvent.change(label, { target: { value: "SeaTalk bot" } });
    fireEvent.blur(label);
    await waitFor(() =>
      expect(api.setNotes).toHaveBeenCalledWith(SEATALK.ref, { label: "SeaTalk bot" }),
    );
    const description = screen.getByRole("textbox", { name: "Description" });
    description.focus();
    fireEvent.change(description, { target: { value: "bot app secret" } });
    fireEvent.keyDown(description, { key: "Enter" });
    await waitFor(() =>
      expect(api.setNotes).toHaveBeenCalledWith(SEATALK.ref, { description: "bot app secret" }),
    );
    // The list is read again, and the address did not move.
    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(1));
    expect(screen.getAllByTestId("where")[0]).toHaveTextContent(at(SEATALK.ref));
  });

  test("a secret with a label is listed and searched by it, with its description", async () => {
    api.list.mockResolvedValue({
      refs: [
        {
          ...ref({ ref: `secret/${HEX}`, uri: `coffer://secret/${HEX}` }),
          label: "Jira PAT",
          description: "release bot's token",
        } as SecretRef,
        OLD,
      ],
    });
    renderPage();
    expect(await screen.findByText("Jira PAT")).toBeInTheDocument();
    expect(screen.getByText("release bot's token")).toBeInTheDocument();
    expect(screen.queryByText(HEX)).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Find a secret" }), {
      target: { value: "RELEASE" },
    });
    expect(screen.getByText("Jira PAT")).toBeInTheDocument();
    expect(screen.queryByText("old-openai-key")).not.toBeInTheDocument();
  });

  acceptance("web-ui", "a secret in use cannot be deleted from the secrets page", async () => {
    renderPage(at(SEATALK.ref));
    await screen.findByRole("region", { name: "Used by" });
    openMenu(SEATALK.ref);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog", { name: "seatalk-app-secret is in use" });
    expect(within(dialog).getByText("SeaTalk")).toBeInTheDocument();
    expect(within(dialog).getByText("Channel")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/channels/u-st",
    );
    // Blocked: only Close, no disabled Delete.
    expect(within(dialog).queryByRole("button", { name: "Delete secret" })).toBeNull();
    expect(api.remove).not.toHaveBeenCalled();
    // The footer's Close, not the corner ×.
    fireEvent.click(within(dialog).getAllByRole("button", { name: "Close" }).at(-1)!);
    expect(screen.getAllByText("seatalk-app-secret").length).toBeGreaterThan(0);
  });

  test("a refusal the daemon answers names what started using it since", async () => {
    api.remove.mockRejectedValueOnce(
      new ApiError("SECRET_IN_USE", "in use", {
        resources: [{ kind: "skill", name: "release-notes", uid: "s-1", slot: null }],
      }),
    );
    renderPage(at(OLD.ref));
    await screen.findByRole("region", { name: "Used by" });
    openMenu(OLD.ref);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete…" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete old-openai-key?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete secret" }));
    const blocked = await screen.findByRole("dialog", { name: "old-openai-key is in use" });
    expect(api.remove).toHaveBeenCalledWith("secret/old-openai-key");
    expect(within(blocked).getByText("release-notes")).toBeInTheDocument();
  });

  test("an unused secret is deleted after confirming, and the page returns to the list", async () => {
    renderPage(at(OLD.ref));
    await screen.findByRole("region", { name: "Used by" });
    openMenu(OLD.ref);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete…" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete old-openai-key?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete secret" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.remove).toHaveBeenCalledWith("secret/old-openai-key");
    await waitFor(() => expect(screen.getAllByTestId("where")[0]).toHaveTextContent(/^\/secrets$/));
  });

  test("the menu holds Copy reference and Delete, not the visible buttons", async () => {
    renderPage(at(SEATALK.ref));
    await screen.findByRole("region", { name: "Used by" });
    expect(screen.getByRole("button", { name: "Replace value…" })).toBeInTheDocument();
    openMenu(SEATALK.ref);
    expect(
      screen.getByRole("menuitem", {
        name: "Copy reference (coffer://secret/seatalk-app-secret)",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Replace|Reveal/ })).toBeNull();
  });

  acceptance("web-ui", "revealing a secret is an explicit, audited read", async () => {
    inShell = true;
    revealSecret.mockResolvedValue("ghp_example_value");
    renderPage(at(SEATALK.ref));
    await screen.findByRole("region", { name: "Used by" });
    expect(screen.queryByText("ghp_example_value")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reveal value…" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Show the value of seatalk-app-secret?",
    });
    expect(revealSecret).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Reveal for 30 s" }));
    expect(await screen.findByText("ghp_example_value")).toBeInTheDocument();
    expect(revealSecret).toHaveBeenCalledWith("secret/seatalk-app-secret");
    expect(screen.getByText(/Recorded in Activity/)).toBeInTheDocument();
    expect(screen.queryByText(/secret_revealed/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Hide" })).toBeNull();
  });

  test("a browser offers no reveal and names the desktop app instead", async () => {
    renderPage(at(SEATALK.ref));
    expect(await screen.findByRole("button", { name: "Reveal in the Coffer app" })).toBeDisabled();
  });

  test("replacing a value stores it at once and says so", async () => {
    renderPage(at(SEATALK.ref));
    fireEvent.click(await screen.findByRole("button", { name: "Replace value…" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Replace the value of seatalk-app-secret",
    });
    expect(dialog).toHaveTextContent("Channel SeaTalk");
    fireEvent.change(within(dialog).getByLabelText("New value"), { target: { value: "new" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Replace value" }));
    expect(await screen.findByText("Replaced the value of seatalk-app-secret")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.set).toHaveBeenCalledWith(SEATALK.ref, "new");
  });

  test("a secret whose new destination waits is marked on its row and its Used by", async () => {
    api.list.mockResolvedValue({
      refs: [
        GITHUB,
        {
          ...SEATALK,
          bindings: [
            {
              approval_id: "a1",
              destination_kind: "channel",
              destination_uid: "u-st",
              slot: "app_secret",
              status: "pending",
            },
          ],
        },
      ],
    });
    renderPage(at(SEATALK.ref));
    const usedBy = await screen.findByRole("region", { name: "Used by" });
    expect(await within(usedBy).findByText("Waiting for approval")).toBeInTheDocument();
    expect(within(usedBy).getByText("app_secret")).toBeInTheDocument();
    expect(
      within(screen.getByRole("group", { name: "Secrets" })).getByText("Waiting for approval"),
    ).toBeInTheDocument();
  });

  test("an address that names no secret says it no longer exists", async () => {
    renderPage(at("secret/gone"));
    expect(await screen.findByText("This secret no longer exists")).toBeInTheDocument();
  });

  acceptance("web-ui", "the secrets page offers to find plaintext keys", async () => {
    api.scan.mockResolvedValue({ findings: [], files_checked: 2, servers_checked: 1 });
    api.list.mockResolvedValue({ refs: [] });
    const first = renderPage();
    expect(await screen.findByText("No secrets yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add secret" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find plaintext keys" })).toBeInTheDocument();
    first.unmount();

    api.list.mockResolvedValue({ refs: [SEATALK] });
    renderPage();
    const find = await screen.findByRole("button", { name: "Find plaintext keys" });
    expect(screen.getByRole("button", { name: "Add secret" })).toBeInTheDocument();
    fireEvent.click(find);
    expect(await screen.findByRole("dialog", { name: "No plaintext keys found" })).toBeVisible();
    expect(api.scan).toHaveBeenCalled();
  });

  test("a failed list says so with a retry", async () => {
    api.list.mockRejectedValue(new ApiError("INTERNAL", "boom"));
    renderPage();
    expect(await screen.findByText("Couldn’t load secrets")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });
});
