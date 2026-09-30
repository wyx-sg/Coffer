// frontend/src/components/knowledge/knowledgeTestHarness.tsx — renders the Knowledge page for tests.
//
// Test-only (imported by `*.test.tsx` files, never by the app): the page at a
// real address inside the four routes it answers to, with a fresh query
// client, the toast and tooltip providers the shell mounts, and the network
// boundary — `@/lib/api/knowledge`, the engine config and the in-flight list —
// answered from `knowledgeTestData.ts`. Each test file mocks those modules
// itself (vi.mock is hoisted per file) and calls `answerFromFixtures` to wire
// the default answers.
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import * as knowledgeApi from "@/lib/api/knowledge";
import { internalEngineApi } from "@/lib/api/internalEngine";
import * as upkeepApi from "@/lib/api/upkeep";
import { KnowledgePage } from "@/pages/KnowledgePage";

import { COLLECTION, DIFF, EDIT, FILES, ITEM, OTHER, PASS, TREES } from "./knowledgeTestData";

/** Where the router is now — rendered so a test can assert the address. A
 *  test-only file, so fast refresh is not a concern here. */
// eslint-disable-next-line react-refresh/only-export-components
function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
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
              <Route path="/knowledge/changes/:version" element={page} />
              <Route path="/knowledge/:uid" element={page} />
              <Route path="/knowledge/:uid/:tab" element={page} />
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

/** The mocked modules' default answers: the fixtures, a model set, nothing in flight. */
export function answerFromFixtures({ modelSet = true }: { modelSet?: boolean } = {}) {
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
    waiting: [
      {
        collection: COLLECTION.name,
        path: ITEM.path,
        title: ITEM.title,
        submitted_by: "codex",
        submitted_at: new Date().toISOString(),
      },
    ],
    next_cursor: null,
  });
  api.getChange.mockResolvedValue({
    change: PASS,
    diffs: PASS.documents.map((d) => ({ ...d, diff: DIFF })),
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
  vi.mocked(internalEngineApi.get).mockResolvedValue({
    model: modelSet ? "claude-haiku" : null,
    curate_owner_machine_id: null,
    default_model_timeout_s: 60,
    model_timeout_s: null,
    transcribe_model: null,
    updated_at: null,
    upkeep: {},
  });
  vi.mocked(upkeepApi.listUpkeepRuns).mockResolvedValue({ runs: [] });
}
