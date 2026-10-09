// src/components/agents/list/AgentRowCells.test.tsx — the Agents list's Default model column (board 2.1.01).
import type { PropsWithChildren } from "react";
import { beforeEach, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AgentOut } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";
import { fakeApi } from "@/test/fakeApi";

import { ModelCell } from "./AgentRowCells";

const call = fakeApi();

function agent(type: "claude_code" | "codex"): AgentOut {
  return {
    uid: `u-${type}`,
    name: type,
    type,
    config_dir: `/Users/me/.${type}`,
    display_name: type,
    model: null,
    tier_models: null,
    version: null,
    install_handoff: null,
    connection_uid: null,
    state: "installed_active",
    created_at: "",
    updated_at: "",
  } as AgentOut;
}

beforeEach(() => {
  call.mockReset();
  call.mockImplementation(async (path: string) => {
    if (path === "/agents/u-codex") return agent("codex");
    if (path === "/agents/u-claude_code") return agent("claude_code");
    if (path === "/agent-providers/codex/models")
      return {
        models: [],
        default_model: null,
        builtin_default: { id: "gpt-5-codex", label: "GPT-5 Codex", description: "" },
        resolved_default: "gpt-5-codex",
      };
    if (path === "/agent-providers/claude_code/models")
      return { models: [], default_model: null, builtin_default: null, resolved_default: null };
    throw new Error(`unexpected ${path}`);
  });
});

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

acceptance("provider-switching", "the built-in default shows its model in the web UI", async () => {
  render(
    <>
      <ModelCell uid="u-codex" type="codex" />
      <ModelCell uid="u-claude_code" type="claude_code" />
    </>,
    { wrapper },
  );
  expect(await screen.findByText("Built-in default (GPT-5 Codex)")).toBeInTheDocument();
  expect(await screen.findByText("Built-in default")).toBeInTheDocument();
});
