// frontend/src/components/agents/AgentAdoptMcpDialog.test.tsx
//
// The adopt dialog turns a direct MCP entry into a Coffer-managed resource:
//   - one keychain-reference input per detected secret key, prefilled
//     mcp/{agent}/{entry}/{KEY}; the submit body carries the mapping
//   - a rename field that stays hidden until the daemon answers 409 with a
//     `suggested_name`; the resubmit then carries `new_name`
//   - 422 ADOPT_SECRET_UNRESOLVED (no suggested_name) shows the message
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentAdoptMcpDialog } from "./AgentAdoptMcpDialog";
import type { McpEntryOut } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    adoptMcpEntry: vi.fn(),
  },
}));

const { agentsApi } = await import("@/lib/api/agents");
const adoptMock = vi.mocked(agentsApi.adoptMcpEntry);

const ENTRY: McpEntryOut = {
  name: "github",
  source: "global",
  transport: "stdio",
  command: "npx",
  args: ["-y", "gh-mcp"],
  env_keys: ["GITHUB_TOKEN"],
  secret_keys: ["GITHUB_TOKEN"],
  url: null,
  header_keys: [],
  enabled: null,
  is_coffer: false,
  matches_resource: null,
};

function renderDialog(entry: McpEntryOut = ENTRY) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <AgentAdoptMcpDialog agentName="cc" entry={entry} open onOpenChange={() => {}} />,
    { wrapper: Wrapper },
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentAdoptMcpDialog", () => {
  test("renders a prefilled keychain-reference input per secret key and submits the mapping", async () => {
    adoptMock.mockResolvedValue({ kind: "mcp_server", name: "github" });
    renderDialog();

    const input = screen.getByLabelText("GITHUB_TOKEN");
    expect(input).toHaveValue("mcp/cc/github/GITHUB_TOKEN");
    expect(screen.getByText(/likely secrets detected/i)).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "mcp/custom/ref" } });
    fireEvent.click(screen.getByRole("button", { name: "Adopt into Coffer" }));

    await waitFor(() =>
      expect(adoptMock).toHaveBeenCalledWith("cc", "github", {
        source: "global",
        secrets: { GITHUB_TOKEN: "mcp/custom/ref" },
      }),
    );
  });

  test("no secret keys → no secret inputs and no secrets in the body", async () => {
    adoptMock.mockResolvedValue({ kind: "mcp_server", name: "plain" });
    renderDialog({ ...ENTRY, name: "plain", env_keys: [], secret_keys: [] });

    expect(screen.queryByText(/likely secrets detected/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Adopt into Coffer" }));
    await waitFor(() => expect(adoptMock).toHaveBeenCalledWith("cc", "plain", { source: "global" }));
  });

  test("409 with suggested_name reveals the prefilled rename field; resubmit sends new_name", async () => {
    adoptMock
      .mockRejectedValueOnce(
        new ApiError("ALREADY_EXISTS", "resource already exists", {
          suggested_name: "github-claude_code",
        }),
      )
      .mockResolvedValueOnce({ kind: "mcp_server", name: "github-claude_code" });
    renderDialog();

    // Rename field hidden until the daemon reports the conflict.
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Adopt into Coffer" }));
    const rename = await screen.findByLabelText("Name");
    expect(rename).toHaveValue("github-claude_code");
    expect(screen.getByText(/name conflict — rename and retry/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Adopt into Coffer" }));
    await waitFor(() =>
      expect(adoptMock).toHaveBeenLastCalledWith("cc", "github", {
        source: "global",
        secrets: { GITHUB_TOKEN: "mcp/cc/github/GITHUB_TOKEN" },
        new_name: "github-claude_code",
      }),
    );
  });

  test("422 ADOPT_SECRET_UNRESOLVED shows the daemon's message", async () => {
    adoptMock.mockRejectedValue(
      new ApiError("ADOPT_SECRET_UNRESOLVED", "secret GITHUB_TOKEN is not in the keychain"),
    );
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Adopt into Coffer" }));
    expect(
      await screen.findByText(/secret GITHUB_TOKEN is not in the keychain/),
    ).toBeInTheDocument();
    // No rename field for a non-conflict error.
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  });
});
