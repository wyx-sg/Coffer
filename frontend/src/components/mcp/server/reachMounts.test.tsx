// src/components/mcp/server/reachMounts.test.tsx — the MCP servers page's reach: read on the row, changed from the header and the selection bar through one control.
import { expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ResourceOut } from "@/lib/api/resources";
import { McpServerHeader } from "./McpServerHeader";
import { McpServerListRow } from "./McpServerListRow";
import { McpServersBulkBar } from "./McpServersBulkBar";

vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useBulkReach: vi.fn(() => ({ disable: vi.fn(), enable: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({
    data: [{ uid: "u-claude-code", type: "claude_code", display_name: "Claude Code" }],
  })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => {
  const stub = () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
    reset: vi.fn(),
  });
  return {
    useEnableResource: vi.fn(stub),
    useDisableResource: vi.fn(stub),
    useDeleteResource: vi.fn(stub),
    useBulkDeleteResources: vi.fn(() => ({ run: vi.fn(), isPending: false })),
  };
});

const FILES = {
  uid: "u-files",
  name: "files",
  kind: "mcp_server",
  title: null,
  enabled: true,
  scope: null,
  config: { transport: { type: "stdio", command: "npx", args: ["-y", "files"] } },
} as unknown as ResourceOut;

acceptance("web-ui", "row, header and selection bar mount the same reach control", () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>
          <ul>
            <McpServerListRow
              resource={FILES}
              detail={{ status: "healthy" } as never}
              tiering={undefined}
              agents={[
                { uid: "u-claude-code", type: "claude_code", display_name: "Claude Code" } as never,
              ]}
              to="/mcp-servers/files"
              current
              checked
              onCheckedChange={vi.fn()}
            />
          </ul>
          <McpServerHeader
            resource={FILES}
            state={{ kind: "healthy", group: "healthy", tone: "ok" }}
            testing={false}
            onTest={vi.fn()}
            onEdit={vi.fn()}
            onOpenLog={vi.fn()}
            onCopyConfig={vi.fn()}
            onTurn={vi.fn()}
            onDelete={vi.fn()}
          />
          <McpServersBulkBar servers={[FILES]} total={1} onDone={vi.fn()} />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );

  /** Open a mount's reach button, read the panel it opens, then close it. */
  const panelOf = (button: HTMLElement) => {
    fireEvent.click(button);
    const radios = screen.getAllByRole("radio").map((r) => r.closest("label")?.textContent);
    const machineLine = screen.getByTestId("reach-machine-local").textContent;
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    return { radios, machineLine };
  };

  // The row reads its reach; it is a link into the pane, not a second control.
  const row = screen.getByRole("listitem");
  expect(row).toHaveTextContent(/all agents/i);
  expect(within(row).queryByTestId("scope-control")).toBeNull();

  const headerButton = within(screen.getByTestId("scope-control")).getByRole("button");
  expect(headerButton).toHaveTextContent(/^every agent$/i);
  const bulkButton = within(screen.getByTestId("bulk-reach-control")).getByRole("button");

  const fromHeader = panelOf(headerButton);
  const fromBulk = panelOf(bulkButton);
  expect(fromHeader.radios).toEqual([
    expect.stringMatching(/^off$/i),
    expect.stringMatching(/every agent/i),
    expect.stringMatching(/only selected agents/i),
  ]);
  expect(fromHeader.machineLine).toBeTruthy();
  expect(fromBulk).toEqual(fromHeader);
});
