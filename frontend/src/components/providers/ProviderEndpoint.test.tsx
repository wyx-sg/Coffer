// src/components/providers/ProviderEndpoint.test.tsx — a key held for approval is shown as that, with
// its next step, and never as an unreachable endpoint with an agent hand-off.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { Provider } from "@/lib/api/providers";
import type { ProbeStatus } from "@/lib/providers/probeStatus";
import { acceptance } from "@/test/acceptance";
import { ProviderEndpoint } from "./ProviderEndpoint";

const KEY = "secret/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

const openSheet = vi.fn();
vi.mock("@/lib/hooks/useApprovals", async (orig) => ({
  ...(await orig<typeof import("@/lib/hooks/useApprovals")>()),
  openApprovalsSheet: () => openSheet(),
}));

vi.mock("@/lib/api/secret", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/secret")>()),
  secretsApi: {
    list: vi.fn(async () => ({ refs: [] })),
    rejectedApprovalsFor: vi.fn(async () => ({ approvals: [{ id: "apr-3" }] })),
    askAgain: vi.fn(async () => undefined),
  },
}));

const PROVIDER = {
  uid: "p1",
  name: "Agnes",
  protocol: "openai",
  base_url: "https://apihub.example.com/v1",
  anthropic_base_url: null,
  secret_ref: KEY,
  local_runtime: null,
} as unknown as Provider;

function show(status: ProbeStatus) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter>
            <ProviderEndpoint
              provider={PROVIDER}
              status={status}
              rejectedStatus={null}
              reason="held"
              onReplaceKey={() => undefined}
            />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("ProviderEndpoint", () => {
  acceptance(
    "provider-switching",
    "a key held for approval says so on the provider page",
    async () => {
      show("awaitingApproval");
      expect(screen.getByText("The API key is waiting for approval")).toBeInTheDocument();
      expect(screen.queryByText(/Can’t reach/)).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Open approvals" }));
      expect(openSheet).toHaveBeenCalled();
    },
  );

  test("a refused key offers Ask again for this provider", async () => {
    const { secretsApi } = await import("@/lib/api/secret");
    show("refused");
    expect(screen.getByText("Sending the API key here was refused")).toBeInTheDocument();
    expect(screen.queryByText(/Can’t reach/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ask again" }));
    await waitFor(() => expect(secretsApi.askAgain).toHaveBeenCalledWith("apr-3"));
    expect(secretsApi.rejectedApprovalsFor).toHaveBeenCalledWith("p1");
  });
});
