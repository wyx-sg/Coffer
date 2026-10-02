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
    scan: vi.fn(),
    importFindings: vi.fn(),
    pendingApprovals: vi.fn(),
    secretBoundary: vi.fn(),
    rejectApproval: vi.fn(),
    refusedApprovals: vi.fn(),
    askAgain: vi.fn(),
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
    ...over,
  };
}

const GITHUB = ref({
  ref: "mcp_server/u-gh/GITHUB_TOKEN",
  cited_by: [{ kind: "mcp_server", name: "github", uid: "u-gh" }],
});
const OPENAI = ref({
  ref: "provider/u-oa/api_key",
  present: false,
  cited_by: [{ kind: "provider", name: "OpenAI", uid: "u-oa" }],
});
const SEATALK = ref({
  ref: "secret/seatalk-app-secret",
  uri: "coffer://secret/seatalk-app-secret",
  cited_by: [{ kind: "channel", name: "SeaTalk", uid: "u-st" }],
});
const OLD = ref({
  ref: "secret/old-openai-key",
  uri: "coffer://secret/old-openai-key",
  unreferenced: true,
  readable_by_local_processes: true,
});

const PENDING = {
  id: "apr-new",
  op: "add_secret" as const,
  status: "pending" as const,
  description: "add the new secret 'npm-publish-token'",
  created_at: "2026-09-30T08:00:00Z",
  requested_by: "ui",
  ref: "secret/npm-publish-token",
  destination_kind: null,
  destination_label: null,
  destination_uid: null,
  slot: null,
  target: null,
  decided_at: null,
  decided_by: null,
};

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname}</p>;
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={["/secrets"]}>
            <Routes>
              <Route path="/secrets" element={<SecretsPage />} />
              <Route path="*" element={<Where />} />
            </Routes>
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const openMenu = (name: string) =>
  fireEvent.click(screen.getByRole("button", { name: `Actions for ${name}` }));

beforeEach(() => {
  inShell = false;
  api.list.mockResolvedValue({ refs: [GITHUB, OPENAI, SEATALK, OLD] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
  api.refusedApprovals.mockResolvedValue({ approvals: [] });
  api.remove.mockResolvedValue(undefined);
  api.set.mockResolvedValue(undefined);
});
afterEach(() => {
  vi.clearAllMocks();
  kindPageOpen = true;
});

describe("SecretsPage", () => {
  acceptance("web-ui", "the secrets page lists each secret with what uses it", async () => {
    renderPage();
    await screen.findByText(GITHUB.ref);
    const inUse = screen.getByRole("region", { name: /In use/ });
    const githubRow = within(inUse).getByText(GITHUB.ref).closest("tr")!;
    const openaiRow = within(inUse).getByText(OPENAI.ref).closest("tr")!;
    expect(within(githubRow).queryByText("Missing on this Mac")).not.toBeInTheDocument();
    expect(within(openaiRow).getByText("Missing on this Mac")).toBeInTheDocument();

    fireEvent.click(within(openaiRow).getByRole("button", { name: /is used by 1 thing/ }));
    expect(await screen.findByText("Model provider")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "OpenAI" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/model-providers/u-oa");
  });

  test("a citer whose feature is off is named without a link to its missing page", async () => {
    kindPageOpen = false;
    renderPage();
    await screen.findByText(GITHUB.ref);
    const inUse = screen.getByRole("region", { name: /In use/ });
    const openaiRow = within(inUse).getByText(OPENAI.ref).closest("tr")!;
    fireEvent.click(within(openaiRow).getByRole("button", { name: /is used by 1 thing/ }));
    expect(await screen.findByText("Model provider")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "OpenAI" })).toBeNull();
  });

  test("a secret nothing uses is listed apart, never used, as safe to delete", async () => {
    renderPage();
    const unused = await screen.findByRole("region", { name: /Not used by anything/ });
    expect(within(unused).getByText("old-openai-key")).toBeInTheDocument();
    expect(within(unused).getByText("Nothing")).toBeInTheDocument();
    expect(within(unused).getByText("Never")).toBeInTheDocument();
    expect(unused).toHaveTextContent("safe to delete");
  });

  test("each row says when it was last used and created, and copies its reference", async () => {
    const used = new Date(Date.now() - 2 * 60_000).toISOString();
    api.list.mockResolvedValue({ refs: [{ ...SEATALK, last_used_at: used }] });
    renderPage();
    const row = (await screen.findByText("seatalk-app-secret")).closest("tr")!;
    expect(row).toHaveTextContent("2 min ago");
    expect(row).toHaveTextContent(/12 Aug|Aug 12/);
    openMenu("seatalk-app-secret");
    expect(
      screen.getByRole("menuitem", {
        name: "Copy reference (coffer://secret/seatalk-app-secret)",
      }),
    ).toBeInTheDocument();
  });

  acceptance("secret", "a secret this Mac cannot open is missing on this Mac", async () => {
    const locked = ref({
      ref: "secret/sentry-token",
      uri: "coffer://secret/sentry-token",
      locked: true,
      cited_by: [{ kind: "mcp_server", name: "sentry", uid: "u-se" }],
    });
    api.list.mockResolvedValue({ refs: [GITHUB, OPENAI, locked] });
    api.set.mockResolvedValueOnce({
      approval: { ...PENDING, op: "replace_value", ref: locked.ref },
    });
    renderPage();
    const banner = await screen.findByTestId("secrets-missing-banner");
    expect(banner).toHaveTextContent("2 secrets have no value on this Mac");
    expect(within(banner).getByRole("link", { name: "Import master key…" })).toHaveAttribute(
      "href",
      "/settings/security",
    );
    const row = screen.getByText("sentry-token").closest("tr")!;
    expect(within(row).getByText("Missing on this Mac")).toBeInTheDocument();
    openMenu("sentry-token");
    expect(screen.getByRole("menuitem", { name: "Reveal in the Coffer app" })).toBeDisabled();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    fireEvent.click(within(row).getByRole("button", { name: "Add a value for sentry-token" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a value for sentry-token" });
    fireEvent.change(within(dialog).getByLabelText("New value"), { target: { value: "sntr" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add value" }));
    expect(await screen.findByText(/Saved, waiting for approval/)).toBeInTheDocument();
    expect(api.set).toHaveBeenCalledWith("secret/sentry-token", "sntr");
  });

  test("search narrows both groups by name", async () => {
    renderPage();
    await screen.findByText("old-openai-key");
    fireEvent.change(screen.getByRole("textbox", { name: "Find a secret" }), {
      target: { value: "seatalk" },
    });
    expect(screen.getByText("seatalk-app-secret")).toBeInTheDocument();
    expect(screen.queryByText("old-openai-key")).not.toBeInTheDocument();
    expect(screen.queryByText(GITHUB.ref)).not.toBeInTheDocument();
  });

  acceptance("web-ui", "a secret in use cannot be deleted from the secrets page", async () => {
    renderPage();
    await screen.findByText("seatalk-app-secret");
    openMenu("seatalk-app-secret");
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog", { name: "seatalk-app-secret is in use" });
    expect(within(dialog).getByText("SeaTalk")).toBeInTheDocument();
    expect(within(dialog).getByText("Channel")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/channels/u-st",
    );
    expect(within(dialog).getByRole("button", { name: "Delete secret" })).toBeDisabled();
    expect(api.remove).not.toHaveBeenCalled();
    // The footer's Close, not the corner ×.
    fireEvent.click(within(dialog).getAllByRole("button", { name: "Close" }).at(-1)!);
    expect(screen.getByText("seatalk-app-secret")).toBeInTheDocument();
  });

  test("a refusal the daemon answers names what started using it since", async () => {
    api.remove.mockRejectedValueOnce(
      new ApiError("SECRET_IN_USE", "in use", {
        resources: [{ kind: "skill", name: "release-notes", uid: "s-1" }],
      }),
    );
    renderPage();
    await screen.findByText("old-openai-key");
    openMenu("old-openai-key");
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete…" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete old-openai-key?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete secret" }));
    const blocked = await screen.findByRole("dialog", { name: "old-openai-key is in use" });
    expect(api.remove).toHaveBeenCalledWith("secret/old-openai-key");
    expect(within(blocked).getByText("release-notes")).toBeInTheDocument();
  });

  test("an unused secret is deleted after confirming", async () => {
    renderPage();
    await screen.findByText("old-openai-key");
    openMenu("old-openai-key");
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete…" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete old-openai-key?" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Delete secret" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.remove).toHaveBeenCalledWith("secret/old-openai-key");
  });

  acceptance("web-ui", "revealing a secret is an explicit, audited read", async () => {
    inShell = true;
    revealSecret.mockResolvedValue("ghp_example_value");
    renderPage();
    await screen.findByText("seatalk-app-secret");
    expect(screen.queryByText("ghp_example_value")).not.toBeInTheDocument();
    openMenu("seatalk-app-secret");
    fireEvent.click(screen.getByRole("menuitem", { name: "Reveal value…" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Show the value of seatalk-app-secret?",
    });
    expect(revealSecret).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Reveal for 30 s" }));
    expect(await screen.findByText("ghp_example_value")).toBeInTheDocument();
    expect(revealSecret).toHaveBeenCalledWith("secret/seatalk-app-secret");
    expect(screen.getByText(/recorded as secret_revealed/)).toBeInTheDocument();
  });

  test("a browser offers no reveal and names the desktop app instead", async () => {
    renderPage();
    await screen.findByText("seatalk-app-secret");
    openMenu("seatalk-app-secret");
    expect(screen.getByRole("menuitem", { name: "Reveal in the Coffer app" })).toBeDisabled();
  });

  test("adding stores a standalone secret under its name, and a taken name offers replace", async () => {
    renderPage();
    await screen.findByText("seatalk-app-secret");
    fireEvent.click(screen.getByRole("button", { name: "Add secret" }));
    const dialog = await screen.findByRole("dialog", { name: "Add secret" });
    const name = within(dialog).getByLabelText("Name");
    fireEvent.change(name, { target: { value: "seatalk-app-secret" } });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("already exists");
    fireEvent.change(name, { target: { value: "npm-publish-token" } });
    fireEvent.change(within(dialog).getByLabelText("Value"), { target: { value: "npm_x" } });
    expect(dialog).toHaveTextContent("coffer://secret/npm-publish-token");
    fireEvent.click(within(dialog).getByRole("button", { name: "Add secret" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.set).toHaveBeenCalledWith("secret/npm-publish-token", "npm_x");
  });

  acceptance(
    "secret",
    "a refused binding says it was refused and can be asked about again",
    async () => {
      const REFUSED = {
        ...PENDING,
        id: "apr-refused",
        op: "bind" as const,
        status: "rejected" as const,
        description: "send GITHUB_TOKEN to the MCP server github",
      };
      api.refusedApprovals.mockResolvedValueOnce({ approvals: [REFUSED] });
      api.refusedApprovals.mockResolvedValue({ approvals: [] });
      api.askAgain.mockResolvedValue({
        approvals: [{ ...REFUSED, id: "apr-again", status: "pending" }],
      });
      renderPage();
      const row = await screen.findByTestId("refused-approval");
      expect(row).toHaveTextContent("send GITHUB_TOKEN to the MCP server github");
      fireEvent.click(within(row).getByRole("button", { name: "Ask again" }));
      await waitFor(() => expect(api.askAgain).toHaveBeenCalledWith("apr-refused"));
      await waitFor(() => expect(screen.queryByTestId("refused-approval")).not.toBeInTheDocument());
    },
  );

  test("a new secret waiting for approval says so, and the banner offers Review", async () => {
    api.set.mockResolvedValueOnce({ approval: PENDING });
    renderPage();
    await screen.findByText("seatalk-app-secret");
    fireEvent.click(screen.getByRole("button", { name: "Add secret" }));
    const dialog = await screen.findByRole("dialog", { name: "Add secret" });
    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: "npm-publish-token" },
    });
    fireEvent.change(within(dialog).getByLabelText("Value"), { target: { value: "npm_x" } });
    api.pendingApprovals.mockResolvedValue({ approvals: [PENDING] });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add secret" }));
    expect(await screen.findByText(/Saved, waiting for approval/)).toBeInTheDocument();
    const entry = await screen.findByTestId("pending-approvals-entry");
    expect(entry).toHaveTextContent("1 change waiting for approval");
    expect(entry).toHaveTextContent("Approve in the Coffer desktop app. You can reject here.");
    expect(within(entry).getByRole("button", { name: "Review" })).toBeInTheDocument();
  });

  test("a secret whose new value waits is marked on its row", async () => {
    api.pendingApprovals.mockResolvedValue({
      approvals: [{ ...PENDING, op: "replace_value", ref: SEATALK.ref }],
    });
    renderPage();
    const row = (await screen.findByText("seatalk-app-secret")).closest("tr")!;
    expect(await within(row).findByText("Waiting for approval")).toBeInTheDocument();
  });

  test("a replaced value that waits for approval says so instead of claiming it took effect", async () => {
    api.set.mockResolvedValueOnce({
      approval: {
        id: "apr-1",
        op: "replace_value",
        status: "pending",
        description: "",
        created_at: "2026-09-30T08:00:00Z",
        requested_by: "web",
        ref: SEATALK.ref,
        destination_kind: null,
        destination_label: null,
        destination_uid: null,
        slot: null,
        target: null,
        decided_at: null,
        decided_by: null,
      },
    });
    renderPage();
    await screen.findByText("seatalk-app-secret");
    openMenu("seatalk-app-secret");
    fireEvent.click(screen.getByRole("menuitem", { name: "Replace value…" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Replace the value of seatalk-app-secret",
    });
    expect(dialog).toHaveTextContent("Channel SeaTalk");
    fireEvent.change(within(dialog).getByLabelText("New value"), { target: { value: "new" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Replace value" }));
    expect(await screen.findByText(/Saved, waiting for approval/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.set).toHaveBeenCalledWith(SEATALK.ref, "new");
  });

  test("first run shows the empty state with both ways in", async () => {
    api.list.mockResolvedValue({ refs: [] });
    renderPage();
    expect(await screen.findByText("No secrets yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add secret" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find plaintext keys" })).toBeInTheDocument();
  });

  test("a failed list says so with a retry", async () => {
    api.list.mockRejectedValue(new ApiError("INTERNAL", "boom"));
    renderPage();
    expect(await screen.findByText("Couldn't load secrets")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });
});
