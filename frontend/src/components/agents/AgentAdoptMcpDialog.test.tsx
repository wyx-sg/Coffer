// src/components/agents/AgentAdoptMcpDialog.test.tsx — adopting one direct MCP entry into Coffer (boards 2.1.27, 2.1.28).
//
// Covered: what the dialog says will happen (file, agent), the name field
// prefilled with the entry's name, every env key with how it is stored, the
// secret reference of a secret key (prefilled from the agent's NAME,
// while the request is addressed by its UID), the pending label, a name
// conflict said under the name field and retried with `new_name`, and any
// other failure shown inline.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentAdoptMcpDialog } from "./AgentAdoptMcpDialog";
import type { McpEntryOut } from "@/lib/api/agents-workspace";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/api/agents", () => ({ agentsApi: { adoptMcpEntry: vi.fn() } }));
const { agentsApi } = await import("@/lib/api/agents");
const adoptMock = vi.mocked(agentsApi.adoptMcpEntry);

const ENTRY: McpEntryOut = {
  name: "postgres-local",
  source: "global",
  transport: "stdio",
  command: "uvx",
  args: ["mcp-server-postgres"],
  env_keys: ["DATABASE_URL", "PGSSLMODE"],
  secret_keys: ["DATABASE_URL"],
  url: null,
  header_keys: [],
  enabled: null,
  is_coffer: false,
  matches_resource: null,
};

function renderDialog(entry: McpEntryOut = ENTRY, onAdopted = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <AgentAdoptMcpDialog
      agentUid="u-cc"
      agentName="cc"
      agentLabel="Claude Code"
      fileLabel="~/.claude.json"
      entry={entry}
      open
      onOpenChange={() => {}}
      onAdopted={onAdopted}
    />,
    { wrapper: Wrapper },
  );
}

const adoptButton = () => screen.getByRole("button", { name: "Adopt" });

afterEach(() => vi.clearAllMocks());

describe("AgentAdoptMcpDialog", () => {
  test("says what adopting does and how each env key is stored", () => {
    renderDialog();
    expect(screen.getByText("Adopt postgres-local")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Coffer serves it through its gateway and takes the entry out of ~/.claude.json, so Claude Code never gets it twice. A backup copy is kept in Coffer’s folder.",
    );
    expect(screen.getByRole("dialog").className).toContain("max-w-[640px]");
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Name in Coffer/)).toHaveValue("postgres-local");
    expect(screen.getByText("uvx mcp-server-postgres")).toBeInTheDocument();
    expect(screen.getByText("Secret")).toBeInTheDocument();
    expect(screen.getByText("Plain value")).toBeInTheDocument();
    expect(screen.getByText(/DATABASE_URL looks like a secret/)).toBeInTheDocument();
  });

  test("submits the secret's secret reference, spelled with the agent's name", async () => {
    const onAdopted = vi.fn();
    adoptMock.mockResolvedValue({ uid: "r-pg", kind: "mcp_server", name: "postgres-local" });
    renderDialog(ENTRY, onAdopted);

    const ref = screen.getByLabelText("Value in Coffer: DATABASE_URL");
    expect(ref).toHaveValue("mcp/cc/postgres-local/DATABASE_URL");
    fireEvent.change(ref, { target: { value: "cred/pg/url" } });
    fireEvent.click(adoptButton());

    await waitFor(() =>
      expect(adoptMock).toHaveBeenCalledWith("u-cc", "postgres-local", {
        source: "global",
        secrets: { DATABASE_URL: "cred/pg/url" },
      }),
    );
    await waitFor(() =>
      expect(onAdopted).toHaveBeenCalledWith(expect.objectContaining({ name: "postgres-local" })),
    );
  });

  test("an entry with no secrets sends none", async () => {
    adoptMock.mockResolvedValue({ uid: "r-plain", kind: "mcp_server", name: "plain" });
    renderDialog({ ...ENTRY, name: "plain", env_keys: [], secret_keys: [] });
    expect(screen.queryByText(/looks like a secret/)).not.toBeInTheDocument();
    fireEvent.click(adoptButton());
    await waitFor(() =>
      expect(adoptMock).toHaveBeenCalledWith("u-cc", "plain", { source: "global" }),
    );
  });

  test("reads Adopting… while the request runs", async () => {
    adoptMock.mockReturnValue(new Promise(() => {}));
    renderDialog();
    fireEvent.click(adoptButton());
    expect(await screen.findByRole("button", { name: "Adopting…" })).toBeDisabled();
  });

  test("a name conflict is said under the name; the retry sends the new name", async () => {
    adoptMock
      .mockRejectedValueOnce(
        new ApiError("ALREADY_EXISTS", "resource already exists", {
          suggested_name: "postgres-local-2",
        }),
      )
      .mockResolvedValueOnce({ uid: "r-pg2", kind: "mcp_server", name: "pg-dev" });
    renderDialog();

    fireEvent.click(adoptButton());
    expect(
      await screen.findByText(
        "A server named postgres-local is already in Coffer. Choose another name.",
      ),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Name in Coffer/), { target: { value: "pg-dev" } });
    fireEvent.click(adoptButton());
    await waitFor(() =>
      expect(adoptMock).toHaveBeenLastCalledWith("u-cc", "postgres-local", {
        source: "global",
        secrets: { DATABASE_URL: "mcp/cc/postgres-local/DATABASE_URL" },
        new_name: "pg-dev",
      }),
    );
  });

  test("any other failure is shown inline", async () => {
    adoptMock.mockRejectedValue(
      new ApiError("ADOPT_SECRET_UNRESOLVED", "secret DATABASE_URL is not in the keychain"),
    );
    renderDialog();
    fireEvent.click(adoptButton());
    expect(
      await screen.findByText(/secret DATABASE_URL is not in the keychain/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/already in Coffer/)).not.toBeInTheDocument();
  });
});
