// src/components/secret/ScanSecretsDialog.test.tsx — Find plaintext keys: findings ticked, a dry run reviewed, then applied.
//
// Only the network boundary (`secretsApi`) is mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { SecretScan } from "@/lib/api/secret";
import { acceptance } from "@/test/acceptance";
import { ScanSecretsDialog } from "./ScanSecretsDialog";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    scan: vi.fn(),
    importFindings: vi.fn(),
    ignoreFindings: vi.fn(),
    unignoreFindings: vi.fn(),
    list: vi.fn(),
    pendingApprovals: vi.fn(),
  },
}));
const { secretsApi } = await import("@/lib/api/secret");
const api = vi.mocked(secretsApi);

const SCAN: SecretScan = {
  files_checked: 12,
  servers_checked: 4,
  findings: [
    {
      id: "f1",
      source: "skill",
      resource: "release-notes",
      resource_uid: "s1",
      path: "/Users/me/.coffer/vault/skills/release-notes/scripts/publish.sh",
      line: 12,
      field: null,
      key: "GITHUB_TOKEN",
      rule: "github-pat",
      proposed_name: "github-token",
      ignored: false,
    },
    {
      id: "f2",
      source: "mcp_server",
      resource: "weather",
      resource_uid: "m1",
      path: null,
      line: null,
      field: "env",
      key: "WEATHER_API_KEY",
      rule: "generic-api-key",
      proposed_name: null,
      ignored: false,
    },
    {
      id: "f3",
      source: "mcp_server",
      resource: "gateway",
      resource_uid: "m2",
      path: null,
      line: null,
      field: "header",
      key: "Authorization",
      rule: "generic-api-key",
      proposed_name: null,
      ignored: false,
    },
  ],
};

const onOpenChange = vi.fn();

function renderDialog(only?: readonly string[]) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ScanSecretsDialog open onOpenChange={onOpenChange} only={only} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const movedOf = (ids: string[]) =>
  SCAN.findings
    .filter((f) => ids.includes(f.id))
    .map((f) => ({
      id: f.id,
      source: f.source,
      resource: f.resource,
      name: f.proposed_name,
      label: f.proposed_name,
      ref: f.source === "mcp_server" ? `mcp_server:${f.resource}:${f.key}` : null,
      uri: f.proposed_name ? `coffer://secret/${f.proposed_name}` : null,
    }));

beforeEach(() => {
  api.scan.mockResolvedValue(SCAN);
  api.list.mockResolvedValue({ refs: [] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
});
afterEach(() => vi.clearAllMocks());

describe("ScanSecretsDialog", () => {
  acceptance("secret", "the dialog hides what is not a secret", async () => {
    const two: SecretScan = { ...SCAN, findings: SCAN.findings.slice(0, 2) };
    const marked: SecretScan = {
      ...two,
      findings: [{ ...two.findings[0], ignored: true }, two.findings[1]],
    };
    api.scan.mockResolvedValue(two);
    api.ignoreFindings.mockResolvedValue(marked);
    api.unignoreFindings.mockResolvedValue(two);
    api.importFindings.mockImplementation(async (ids, dryRun) => ({
      dry_run: dryRun,
      moved: movedOf(ids),
      skipped: [],
    }));
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: "Not a secret: release-notes release-notes/scripts/publish.sh:12",
      }),
    );
    await waitFor(() => expect(api.ignoreFindings).toHaveBeenCalledWith(["f1"]));
    await waitFor(() =>
      expect(within(dialog).queryByText("release-notes/scripts/publish.sh:12")).toBeNull(),
    );
    expect(within(dialog).getByText("1 of 1 ticked")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Show ignored (1)" }));
    expect(within(dialog).getByText("release-notes/scripts/publish.sh:12")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 1 change" }));
    await screen.findByRole("dialog", { name: "Review changes" });
    expect(api.importFindings).toHaveBeenCalledWith(["f2"], true);
  });

  test("Report again brings an ignored finding back", async () => {
    const marked: SecretScan = {
      ...SCAN,
      findings: [{ ...SCAN.findings[0], ignored: true }, ...SCAN.findings.slice(1)],
    };
    api.scan.mockResolvedValue(marked);
    api.unignoreFindings.mockResolvedValue(SCAN);
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Show ignored (1)" }));
    fireEvent.click(within(dialog).getByRole("button", { name: /^Report again/ }));
    await waitFor(() => expect(api.unignoreFindings).toHaveBeenCalledWith(["f1"]));
    expect(await within(dialog).findByText("3 of 3 ticked")).toBeInTheDocument();
  });

  test("groups findings by source with place and what each becomes, all ticked, no value", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    expect(dialog).toHaveTextContent("3 found in 3 places");
    expect(within(dialog).getByText("Skills")).toBeInTheDocument();
    expect(within(dialog).getByText("MCP servers")).toBeInTheDocument();
    expect(within(dialog).getByText("release-notes/scripts/publish.sh:12")).toBeInTheDocument();
    expect(within(dialog).getByText("coffer://secret/github-token")).toBeInTheDocument();
    expect(within(dialog).getByText("env WEATHER_API_KEY")).toBeInTheDocument();
    expect(within(dialog).getByText("header Authorization")).toBeInTheDocument();
    expect(within(dialog).getByText("github-pat")).toBeInTheDocument();
    expect(within(dialog).getAllByText("The server's own secret")).toHaveLength(2);
    expect(within(dialog).getByText("3 of 3 ticked")).toBeInTheDocument();
  });

  test("review runs a dry run of the ticked findings; apply runs the import", async () => {
    api.importFindings.mockImplementation(async (ids, dryRun) => ({
      dry_run: dryRun,
      moved: movedOf(ids),
      skipped: [],
    }));
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(
      within(dialog).getByRole("checkbox", { name: "Move gateway header Authorization" }),
    );
    expect(within(dialog).getByText("2 of 3 ticked")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 2 changes" }));

    const preview = await screen.findByRole("dialog", { name: "Review changes" });
    expect(api.importFindings).toHaveBeenCalledWith(["f1", "f2"], true);
    expect(preview).toHaveTextContent("2 secrets added, 2 files and servers changed");
    expect(within(preview).getByText("github-token")).toBeInTheDocument();
    expect(within(preview).getByText("weather · WEATHER_API_KEY")).toBeInTheDocument();
    expect(within(preview).getByText("release-notes/scripts/publish.sh")).toBeInTheDocument();
    expect(within(preview).getByText("weather")).toBeInTheDocument();

    fireEvent.click(within(preview).getByRole("button", { name: "Apply 2 changes" }));
    await waitFor(() => expect(api.importFindings).toHaveBeenCalledWith(["f1", "f2"], false));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a finding skipped on apply is named with its reason and the dialog stays", async () => {
    api.importFindings
      .mockResolvedValueOnce({ dry_run: true, moved: movedOf(["f1"]), skipped: [] })
      .mockResolvedValueOnce({
        dry_run: false,
        moved: [],
        skipped: [
          {
            id: "f1",
            source: "skill",
            resource: "release-notes",
            name: "github-token",
            stored: false,
            reason: "secret 'github-token' already holds another value",
          },
        ],
      });
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Tick all" }));
    fireEvent.click(
      within(dialog).getByRole("checkbox", {
        name: "Move release-notes release-notes/scripts/publish.sh:12",
      }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 1 change" }));
    const preview = await screen.findByRole("dialog", { name: "Review changes" });
    fireEvent.click(within(preview).getByRole("button", { name: "Apply 1 change" }));
    const result = await screen.findByRole("dialog", { name: "Moved 0 of 1 key" });
    expect(result).toHaveTextContent("already holds another value");
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  acceptance("secret", "a file that cannot be rewritten keeps its key and says so", async () => {
    const skipped = {
      id: "f1",
      source: "skill" as const,
      resource: "release-notes",
      name: "github-token",
      stored: true,
      reason: "couldn't be rewritten: it is read-only",
    };
    api.importFindings
      .mockResolvedValueOnce({ dry_run: true, moved: movedOf(["f1"]), skipped: [] })
      .mockResolvedValueOnce({ dry_run: false, moved: [], skipped: [skipped] })
      .mockResolvedValueOnce({ dry_run: false, moved: movedOf(["f1"]), skipped: [] });
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Tick all" }));
    fireEvent.click(
      within(dialog).getByRole("checkbox", {
        name: "Move release-notes release-notes/scripts/publish.sh:12",
      }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 1 change" }));
    const preview = await screen.findByRole("dialog", { name: "Review changes" });
    fireEvent.click(within(preview).getByRole("button", { name: "Apply 1 change" }));
    const result = await screen.findByRole("dialog", { name: "Moved 0 of 1 key" });
    expect(result).toHaveTextContent(
      "couldn't be rewritten: it is read-only. The value is stored as github-token",
    );
    expect(result).toHaveTextContent("Every change is in Activity");
    expect(within(result).getByText("Saved · not changed")).toBeInTheDocument();
    expect(result).toHaveClass("max-w-[640px]");
    fireEvent.click(within(result).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(api.importFindings).toHaveBeenLastCalledWith(["f1"], false));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a scan that finds nothing says how many files and servers it read", async () => {
    api.scan.mockResolvedValue({ findings: [], files_checked: 12, servers_checked: 1 });
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "No plaintext keys found" });
    expect(dialog).toHaveTextContent("12 files, 1 server");
    expect(dialog).toHaveClass("max-w-[480px]");
  });

  test("the findings table stays inside the panel", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    const table = within(dialog).getByRole("table");
    expect(table).toHaveClass("table-fixed");
    expect(table.parentElement).toHaveClass("overflow-auto", "min-w-0");
    expect(dialog).toHaveClass("grid-cols-[minmax(0,1fr)]");
  });

  acceptance(
    "vault-sync",
    "the Sync page names each place and offers Move into secrets and push anyway",
    async () => {
      // From the Sync page: only the flagged files' findings, vault-relative.
      api.importFindings.mockImplementation(async (ids, dryRun) => ({
        dry_run: dryRun,
        moved: movedOf(ids),
        skipped: [],
      }));
      renderDialog(["skills/release-notes/scripts/publish.sh", "knowledge/team/db.md"]);
      const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
      expect(dialog).toHaveTextContent("1 found in 1 place");
      expect(within(dialog).getByText("release-notes/scripts/publish.sh:12")).toBeInTheDocument();
      expect(within(dialog).queryByText("env WEATHER_API_KEY")).toBeNull();
      fireEvent.click(within(dialog).getByRole("button", { name: "Review 1 change" }));
      await screen.findByRole("dialog", { name: "Review changes" });
      expect(api.importFindings).toHaveBeenCalledWith(["f1"], true);
    },
  );

  test("flagged files with nothing Coffer can move say so", async () => {
    renderDialog(["knowledge/team/db.md"]);
    const dialog = await screen.findByRole("dialog", { name: "Nothing here Coffer can move" });
    expect(dialog).toHaveTextContent("Coffer moves values out of skill files");
  });
});
