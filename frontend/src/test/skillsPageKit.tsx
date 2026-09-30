// frontend/src/test/skillsPageKit.tsx
// Shared fixtures for the Skills page suites: a skill and an agent row shaped
// like the wire, and a renderer that mounts the page at an address the way the
// router does (all three skills addresses render the same page), and where
// the router ended up. Each suite mocks the api modules
// itself (vi.mock is hoisted per file).
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { AgentOut } from "@/lib/api/agents";
import type { SkillOut } from "@/lib/api/skills";
import { SkillsPage } from "@/pages/SkillsPage";

export function makeSkill(over: Partial<SkillOut> = {}): SkillOut {
  return {
    uid: "sk-11aa",
    name: "hello",
    description: "Say hello nicely.",
    source: { type: "local_import", original_path: "/tmp/hello" },
    builtin: false,
    enabled: true,
    scope: null,
    version_hash: "deadbeefcafe1234",
    master_missing: false,
    master_path: "/Users/me/.coffer/skills/hello",
    last_synced_from_source_at: null,
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    bindings: [],
    requires: [],
    source_status: null,
    ...over,
  };
}

export const BUILTIN_SKILL = makeSkill({
  uid: "sk-guide",
  name: "coffer-guide",
  description: "Coffer's manual.",
  source: { type: "builtin" },
  builtin: true,
  master_path: "/Users/me/.coffer/skills/coffer-guide",
});

export function makeAgent(over: Partial<AgentOut> = {}): AgentOut {
  return {
    uid: "ag-cc",
    name: "claude-code",
    display_name: "Claude Code",
    type: "claude_code",
    config_dir: "/Users/me/.claude",
    state: "installed_active",
    model: null,
    effort: null,
    tier_models: null,
    version: null,
    wire_api: null,
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    ...over,
  } as AgentOut;
}

let router: ReturnType<typeof createMemoryRouter> | null = null;

/** Where the router is now — path and query. */
export const where = {
  get url(): string {
    const loc = router?.state.location;
    return loc ? loc.pathname + loc.search : "";
  },
};

/** Mount the Skills page at `url`, routed as router.tsx routes it. */
export function renderSkillsPage(url = "/skills") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  router = createMemoryRouter(
    [
      { path: "/skills", element: <SkillsPage /> },
      { path: "/skills/:name", element: <SkillsPage /> },
      { path: "/skills/:name/:tab", element: <SkillsPage /> },
      { path: "/clis/:command", element: <div>cli page</div> },
      { path: "/agents", element: <div>agents page</div> },
    ],
    { initialEntries: [url] },
  );
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}
