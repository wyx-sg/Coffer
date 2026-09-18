// frontend/src/lib/hooks/useTemplateEditor.test.ts
//
// The editor holds no draft (FR-062): every edit is computed from what the
// cache currently holds and written straight back. That makes ONE thing
// load-bearing, and it is what this file is for — two edits issued before the
// first has come back must build on each other. If a save only invalidated,
// the cache would still hold the pre-save config until the refetch landed, and
// the second edit would be computed from it and silently undo the first.
//
// Tested here rather than through the page because there is no longer a
// surface that fires two writes in one gesture: everything on the map now goes
// through a dialog. The invariant did not stop mattering when its most
// convenient trigger did — a task dialog saved and a task deleted a moment
// later still land in this queue.
import { describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { resourceKey } from "@/lib/api/queryKeys";
import type { TemplateConfig } from "@/lib/api/workflow";
import { useTemplateEditor } from "@/lib/hooks/useTemplateEditor";

const patch = vi.fn();
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { update: (...args: unknown[]) => patch(...args) },
}));

function stage(key: string): TemplateConfig["stages"][number] {
  return {
    key,
    name: key,
    optional: false,
    nodes: [{ key: `${key}_task`, name: "Task", type: "ai" }],
  };
}

describe("useTemplateEditor", () => {
  test("a second edit issued before the first returns builds on it", async () => {
    patch.mockResolvedValue(undefined);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(resourceKey("wf1"), {
      uid: "wf1",
      kind: "workflow",
      name: "delivery",
      description: null,
      enabled: true,
      config: { description: null, stages: [stage("a")], edges: [] } as TemplateConfig,
    });

    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: qc }, children);
    const { result } = renderHook(() => useTemplateEditor("wf1"), { wrapper });

    const append = (key: string) => (config: TemplateConfig) => ({
      ...config,
      stages: [...config.stages, stage(key)],
    });
    // Both issued before either has resolved — the queue is what makes the
    // second read the first one's result.
    const first = result.current.apply(append("b"));
    const second = result.current.apply(append("c"));
    await Promise.all([first, second]);

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
    const written = patch.mock.calls[1][1] as { config: TemplateConfig };
    // Three, not two: the second edit saw the stage the first one wrote.
    expect(written.config.stages.map((s) => s.key)).toEqual(["a", "b", "c"]);
  });
});
