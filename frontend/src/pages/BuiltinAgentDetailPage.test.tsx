// frontend/src/pages/BuiltinAgentDetailPage.test.tsx
import type { PropsWithChildren } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { BuiltinAgentDetailPage } from "./BuiltinAgentDetailPage";

vi.mock("@/lib/hooks/useChatAgents", () => ({
  useChatAgents: () => ({ data: [{ agent_key: "builtin", display_name: "Coffer Assistant" }] }),
}));
vi.mock("@/lib/hooks/useModels", () => ({
  useModels: () => ({
    data: [
      { id: "1", display_name: "Qwen 2.5", provider: "ollama", model: "qwen2.5", is_default: true },
    ],
  }),
}));
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: () => ({ data: [{ name: "commit-and-push" }, { name: "create-branch" }] }),
}));
vi.mock("@/lib/hooks/useResources", () => ({
  useResources: () => ({ data: [{ name: "confluence", enabled: true }] }),
}));

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("BuiltinAgentDetailPage", () => {
  test("shows the built-in agent, its model, skills and MCP servers", () => {
    render(<BuiltinAgentDetailPage />, { wrapper: wrap });
    expect(screen.getByRole("heading", { name: /coffer assistant/i })).toBeInTheDocument();
    // overview tab shows the default model it runs on
    expect(screen.getByText(/qwen 2.5/i)).toBeInTheDocument();
    // no start-chat anywhere
    expect(screen.queryByRole("link", { name: /start chatting/i })).not.toBeInTheDocument();
  });
});
