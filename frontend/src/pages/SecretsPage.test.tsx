// src/pages/SecretsPage.test.tsx — the Secrets page: the list with what uses each secret, add, delete refused while in use, and reveal only in the desktop app.
//
// Only the network boundary (`credentialsApi`) and the desktop shell's seam
// (`@/lib/tauri`) are mocked; the query client, router and i18n are real.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import type { CredentialRef } from "@/lib/api/credentials";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { SecretsPage } from "./SecretsPage";

vi.mock("@/lib/api/credentials", () => ({
  credentialsApi: {
    list: vi.fn(),
    set: vi.fn(),
    remove: vi.fn(),
    scan: vi.fn(),
    importFindings: vi.fn(),
    pendingApprovals: vi.fn(),
    secretBoundary: vi.fn(),
    rejectApproval: vi.fn(),
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

const { credentialsApi } = await import("@/lib/api/credentials");
const api = vi.mocked(credentialsApi);

function ref(over: Partial<CredentialRef> & { ref: string }): CredentialRef {
  return {
    bindings: [],
    cited_by: [],
    mentioned_by_skills: [],
    present: true,
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
      <TooltipProvider>
        <MemoryRouter initialEntries={["/secrets"]}>
          <Routes>
            <Route path="/secrets" element={<SecretsPage />} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const openMenu = (name: string) =>
  fireEvent.click(screen.getByRole("button", { name: `Actions for ${name}` }));

beforeEach(() => {
  inShell = false;
  api.list.mockResolvedValue({ refs: [GITHUB, OPENAI, SEATALK, OLD] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
  api.remove.mockResolvedValue(undefined);
  api.set.mockResolvedValue(undefined);
});
afterEach(() => vi.clearAllMocks());

describe("SecretsPage", () => {
  // Scenario (revise-web-ui-ia): "the secrets page lists each secret with what uses it"
  test("lists a stored and a missing ref, each naming its citer, which opens that page", async () => {
    renderPage();
    await screen.findByText(GITHUB.ref);
    const inUse = screen.getByRole("region", { name: /In use/ });
    const githubRow = within(inUse).getByText(GITHUB.ref).closest("tr")!;
    const openaiRow = within(inUse).getByText(OPENAI.ref).closest("tr")!;
    expect(within(githubRow).queryByText("Missing")).not.toBeInTheDocument();
    expect(within(openaiRow).getByText("Missing")).toBeInTheDocument();

    fireEvent.click(within(openaiRow).getByRole("button", { name: /is used by 1 thing/ }));
    expect(await screen.findByText("Model provider")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "OpenAI" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/model-providers/u-oa");
  });

  test("a secret nothing uses is listed apart, with its reference, as safe to delete", async () => {
    renderPage();
    const unused = await screen.findByRole("region", { name: /Not used by anything/ });
    expect(within(unused).getByText("old-openai-key")).toBeInTheDocument();
    expect(within(unused).getByText("coffer://secret/old-openai-key")).toBeInTheDocument();
    expect(within(unused).getByText("Nothing")).toBeInTheDocument();
    expect(unused).toHaveTextContent("safe to delete");
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

  // Scenario (revise-web-ui-ia): "a secret in use cannot be deleted from the secrets page"
  test("deleting a secret a channel uses names the channel, sends nothing, and keeps the row", async () => {
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
      new ApiError("CREDENTIAL_IN_USE", "in use", {
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

  // Scenario (revise-web-ui-ia): "revealing a secret is an explicit, audited read"
  test("no value is on the page until Reveal is chosen in the desktop app", async () => {
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
    expect(screen.getByText(/recorded as credential_revealed/)).toBeInTheDocument();
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
    expect(
      await screen.findByRole("dialog", { name: "Saved, waiting for approval" }),
    ).toBeInTheDocument();
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
