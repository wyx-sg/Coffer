// frontend/src/test/knowledgeHarness.tsx — renders the Knowledge page for tests.
//
// Test-only (imported by `*.test.tsx` files, never by the app): the page at a
// real address inside the routes it answers to, with a fresh query client, the
// toast and tooltip providers the shell mounts, and the network boundary —
// `@/lib/api/knowledge` — answered from `knowledgeTestData.ts`. Each test file mocks those modules
// itself (vi.mock is hoisted per file) and calls `answerFromFixtures` to wire
// the default answers.
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import * as knowledgeApi from "@/lib/api/knowledge";
import { readHandoffState } from "@/lib/conversations/handoff";
import { KnowledgePage } from "@/pages/KnowledgePage";

import {
  COLLECTION,
  DIFF,
  EDIT,
  FILES,
  OTHER,
  PASS,
  TREES,
} from "@/components/knowledge/knowledgeTestData";

/** Where the router is now — rendered so a test can assert the address. A
 *  test-only file, so fast refresh is not a concern here. */
// eslint-disable-next-line react-refresh/only-export-components
function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

/** The draft a hand-off opens, rendered as what it carries (agent, prompt, whether it sends itself). */
// eslint-disable-next-line react-refresh/only-export-components
function Draft() {
  const handoff = readHandoffState(useLocation().state);
  return (
    <output data-testid="draft">
      {handoff
        ? `${handoff.agentKey}|${handoff.autoSend ? "send" : "draft"}|${handoff.prompt}`
        : "empty"}
    </output>
  );
}

export function renderKnowledge(path: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const page = <KnowledgePage />;
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path="/knowledge" element={page} />
              <Route path="/knowledge/:uid" element={page} />
              <Route path="/knowledge/:uid/:tab" element={page} />
              <Route path="/conversations/new" element={<Draft />} />
              <Route path="/settings/:tab" element={<p>settings open</p>} />
              <Route path="/activity" element={<p>activity open</p>} />
            </Routes>
            <Where />
          </MemoryRouter>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return qc;
}

/** The mocked module's default answers: the fixtures. */
export function answerFromFixtures() {
  const api = vi.mocked(knowledgeApi);
  api.listCollections.mockResolvedValue({ collections: [COLLECTION, OTHER] });
  api.getTree.mockImplementation(
    async (path: string) => TREES[path] ?? { path, directories: [], files: [] },
  );
  api.getFile.mockImplementation(async (path: string) => {
    const found = FILES[path];
    if (!found) throw new Error(`no fixture for ${path}`);
    return found;
  });
  api.listChanges.mockResolvedValue({
    changes: [PASS, EDIT],
    next_cursor: null,
  });
  api.getHistory.mockResolvedValue({ path: "", versions: [] });
  api.getVersionDiff.mockImplementation(async (path: string, version: string) => ({
    path,
    version,
    status: "modified",
    added: 1,
    removed: 1,
    diff: DIFF,
  }));
}
