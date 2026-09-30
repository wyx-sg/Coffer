// src/components/secret/ScanSecretsDialog.test.tsx — Find plaintext keys: findings ticked, a dry run reviewed, then applied.
//
// Only the network boundary (`secretsApi`) is mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { SecretScan } from "@/lib/api/secret";
import { ScanSecretsDialog } from "./ScanSecretsDialog";

vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    scan: vi.fn(),
    importFindings: vi.fn(),
    list: vi.fn(),
    pendingApprovals: vi.fn(),
  },
}));
const { secretsApi } = await import("@/lib/api/secret");
const api = vi.mocked(secretsApi);

const SCAN: SecretScan = {
  files_checked: 3,
  findings: [
    {
      id: "f1",
      key: "NPM_TOKEN",
      line: 1,
      path: "/Users/me/.coffer/secrets/npm.env",
      proposed_name: "npm-publish-token",
      source: "secrets_file",
    },
    {
      id: "f2",
      key: "AWS_ACCESS_KEY_ID",
      line: 1,
      path: "/Users/me/.coffer/secrets/aws.env",
      proposed_name: "aws-access-key",
      source: "secrets_file",
    },
    {
      id: "f3",
      key: "GITHUB_TOKEN",
      line: 12,
      path: "/Users/me/.coffer/skills/release-notes/scripts/publish.sh",
      proposed_name: "github-token",
      source: "skill",
    },
  ],
  mentions: [
    {
      line: 4,
      mention: "~/.coffer/secrets/aws.env",
      path: "/Users/me/.coffer/skills/deploy/SKILL.md",
      skill: "deploy",
    },
  ],
};

const onOpenChange = vi.fn();

function renderDialog() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ScanSecretsDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.scan.mockResolvedValue(SCAN);
  api.list.mockResolvedValue({ refs: [] });
  api.pendingApprovals.mockResolvedValue({ approvals: [] });
});
afterEach(() => vi.clearAllMocks());

describe("ScanSecretsDialog", () => {
  test("lists each finding by file, line, key and proposed name, all ticked, with no value", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    expect(dialog).toHaveTextContent("3 found in 3 files");
    expect(within(dialog).getByText("~/.coffer/secrets/npm.env")).toBeInTheDocument();
    expect(within(dialog).getByText("npm-publish-token")).toBeInTheDocument();
    expect(within(dialog).getByText("GITHUB_TOKEN")).toBeInTheDocument();
    expect(within(dialog).getByText("3 of 3 ticked")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("1 skill still points at ~/.coffer/secrets/");
  });

  test("review runs a dry run of the ticked findings; apply runs the import", async () => {
    api.importFindings.mockImplementation(async (ids, dryRun) => ({
      dry_run: dryRun,
      moved: SCAN.findings
        .filter((f) => ids.includes(f.id))
        .map((f) => ({
          id: f.id,
          name: f.proposed_name,
          path: f.path,
          uri: `coffer://secret/${f.proposed_name}`,
        })),
      skipped: [],
    }));
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(
      within(dialog).getByRole("checkbox", {
        name: "Move ~/.coffer/skills/release-notes/scripts/publish.sh line 12",
      }),
    );
    expect(within(dialog).getByText("2 of 3 ticked")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 2 changes" }));

    const preview = await screen.findByRole("dialog", { name: "Review changes" });
    expect(api.importFindings).toHaveBeenCalledWith(["f1", "f2"], true);
    expect(preview).toHaveTextContent("2 secrets added, 2 files changed");
    expect(within(preview).getByText("aws-access-key")).toBeInTheDocument();
    expect(within(preview).getByText("~/.coffer/secrets/aws.env")).toBeInTheDocument();

    fireEvent.click(within(preview).getByRole("button", { name: "Apply 4 changes" }));
    await waitFor(() => expect(api.importFindings).toHaveBeenCalledWith(["f1", "f2"], false));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a finding skipped on apply is named with its reason and the dialog stays", async () => {
    api.importFindings
      .mockResolvedValueOnce({
        dry_run: true,
        moved: [{ id: "f1", name: "npm-publish-token", path: SCAN.findings[0].path, uri: "" }],
        skipped: [],
      })
      .mockResolvedValueOnce({
        dry_run: false,
        moved: [],
        skipped: [
          {
            id: "f1",
            name: "npm-publish-token",
            path: SCAN.findings[0].path,
            stored: false,
            reason: "secret 'npm-publish-token' already holds another value",
          },
        ],
      });
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Tick all" }));
    fireEvent.click(
      within(dialog).getByRole("checkbox", { name: "Move ~/.coffer/secrets/npm.env line 1" }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 1 change" }));
    const preview = await screen.findByRole("dialog", { name: "Review changes" });
    fireEvent.click(within(preview).getByRole("button", { name: "Apply 2 changes" }));
    const result = await screen.findByRole("dialog", { name: "Moved 0 of 1 key" });
    expect(result).toHaveTextContent("already holds another value");
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  test("a file that cannot be rewritten keeps its key, says so, and can be tried again", async () => {
    const path = SCAN.findings[0].path;
    const partial = {
      dry_run: false,
      moved: [],
      skipped: [
        {
          id: "f1",
          path,
          name: "npm-publish-token",
          stored: true,
          reason: "couldn't be rewritten: it is read-only",
        },
      ],
    };
    api.importFindings
      .mockResolvedValueOnce({
        dry_run: true,
        moved: [{ id: "f1", name: "npm-publish-token", path, uri: "" }],
        skipped: [],
      })
      .mockResolvedValueOnce(partial)
      .mockResolvedValueOnce({
        dry_run: false,
        moved: [{ id: "f1", name: "npm-publish-token", path, uri: "" }],
        skipped: [],
      });
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Plaintext keys found" });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Tick all" }));
    fireEvent.click(
      within(dialog).getByRole("checkbox", { name: "Move ~/.coffer/secrets/npm.env line 1" }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Review 1 change" }));
    const preview = await screen.findByRole("dialog", { name: "Review changes" });
    fireEvent.click(within(preview).getByRole("button", { name: "Apply 2 changes" }));
    const result = await screen.findByRole("dialog", { name: "Moved 0 of 1 key" });
    expect(result).toHaveTextContent(
      "couldn't be rewritten: it is read-only. The key is saved as the secret npm-publish-token",
    );
    expect(result).toHaveTextContent("Every change is in Activity");
    fireEvent.click(within(result).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(api.importFindings).toHaveBeenLastCalledWith(["f1"], false));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  test("a scan that finds nothing says how many files it read", async () => {
    api.scan.mockResolvedValue({ findings: [], mentions: [], files_checked: 214 });
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "No plaintext keys found" });
    expect(dialog).toHaveTextContent("Coffer checked 214 files and found no API keys or tokens");
  });
});
