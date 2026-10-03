// src/components/IgnoredHere.test.tsx — an item ignored on Overview comes back from its own page.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { PageHeader } from "./PageHeader";

const { read, unignore } = vi.hoisted(() => ({ read: vi.fn(), unignore: vi.fn() }));
vi.mock("@/lib/api/attention", () => ({ attentionApi: { read, unignore } }));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));

const IGNORED = {
  key: "mcp_server:s1:failing",
  kind: "mcp_server",
  uid: "s1",
  title: "github",
  reason: "It failed its last test.",
};

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <PageHeader title="github" subtitle="MCP server" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IgnoredHere", () => {
  acceptance("web-ui", "an ignored item can be shown again from its own page", async () => {
    read.mockResolvedValue({ items: [], errors: [], counts_by_kind: {}, ignored: [IGNORED] });
    unignore.mockResolvedValue(undefined);
    renderAt("/mcp-servers/github");
    expect(await screen.findByText(/It failed its last test\. — ignored on Overview\./)).toBeInTheDocument();
    read.mockResolvedValue({ items: [IGNORED], errors: [], counts_by_kind: {}, ignored: [] });
    fireEvent.click(screen.getByRole("button", { name: "Show it again" }));
    await waitFor(() => expect(unignore).toHaveBeenCalledWith(IGNORED.key));
    await waitFor(() => expect(screen.queryByText(/ignored on Overview/)).toBeNull());
  });

  test("another page shows no ignored line", async () => {
    read.mockResolvedValue({ items: [], errors: [], counts_by_kind: {}, ignored: [IGNORED] });
    renderAt("/skills/github");
    await waitFor(() => expect(read).toHaveBeenCalled());
    expect(screen.queryByText(/ignored on Overview/)).toBeNull();
  });
});
