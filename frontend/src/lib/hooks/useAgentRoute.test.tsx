// src/lib/hooks/useAgentRoute.test.tsx — type → uid, and the old uid / ?tab= / Conversations addresses redirected.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { useAgentRoute } from "./useAgentRoute";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgentTypes: vi.fn(),
  useAgent: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useAgents");

const ROWS = [
  { type: "claude_code", uid: "agt_cc", state: "installed_active" },
  { type: "codex", uid: null, state: "installed_active" },
];
const AGENT = { uid: "agt_cc", type: "claude_code", name: "claude-code" };

function mockData() {
  vi.mocked(hooks.useAgentTypes).mockReturnValue({
    data: ROWS,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useAgentTypes>);
  vi.mocked(hooks.useAgent).mockImplementation(
    (uid: string) =>
      ({
        data: uid === "agt_cc" ? AGENT : undefined,
        isPending: false,
        error: uid !== "" && uid !== "agt_cc" ? new Error("not found") : null,
      }) as unknown as ReturnType<typeof hooks.useAgent>,
  );
}

function Probe() {
  const route = useAgentRoute();
  const { pathname, search } = useLocation();
  return (
    <output data-testid="probe">
      {JSON.stringify({
        at: pathname + search,
        type: route.type,
        uid: route.uid,
        notAdded: route.notAdded,
        redirecting: route.redirecting,
      })}
    </output>
  );
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/agents/:type" element={<Probe />} />
        <Route path="/agents/:type/:tab" element={<Probe />} />
        <Route path="/agents/:type/memory/store" element={<Probe />} />
        <Route path="/agents/:type/mcp-servers/:entry" element={<Probe />} />
      </Routes>
    </MemoryRouter>,
  );
  return () => JSON.parse(screen.getByTestId("probe").textContent ?? "{}");
}

afterEach(() => vi.clearAllMocks());

describe("useAgentRoute", () => {
  test("a type address resolves the registered agent's uid", () => {
    mockData();
    const probe = renderAt("/agents/claude_code/skills");
    expect(probe()).toMatchObject({
      at: "/agents/claude_code/skills",
      type: "claude_code",
      uid: "agt_cc",
      notAdded: false,
      redirecting: false,
    });
  });

  test("a supported type with no agent reads as not added", () => {
    mockData();
    const probe = renderAt("/agents/codex");
    expect(probe()).toMatchObject({ type: "codex", uid: "", notAdded: true });
  });

  test("an old uid address is replaced by the type, the rest kept", () => {
    mockData();
    const probe = renderAt("/agents/agt_cc/mcp-servers/github?source=x");
    expect(probe()).toMatchObject({
      at: "/agents/claude_code/mcp-servers/github?source=x",
      type: "claude_code",
    });
  });

  test("old tab forms land on today's tab", () => {
    mockData();
    expect(renderAt("/agents/agt_cc?tab=mcpServers")()).toMatchObject({
      at: "/agents/claude_code/mcp-servers",
    });
  });

  test("the old Conversations session page opens the session on the Sessions tab", () => {
    mockData();
    expect(renderAt("/agents/claude_code/conversations?path=%2Fs.jsonl")()).toMatchObject({
      at: "/agents/claude_code/sessions?session=%2Fs.jsonl",
    });
  });

  test("an old memory-store address moves under /memory/store", () => {
    mockData();
    expect(renderAt("/agents/agt_cc/memory?dir=%2Fm")()).toMatchObject({
      at: "/agents/claude_code/memory/store?dir=%2Fm",
    });
  });
});
