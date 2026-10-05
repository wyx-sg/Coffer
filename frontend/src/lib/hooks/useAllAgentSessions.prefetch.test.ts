import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { agentSessionsApi } from "@/lib/api/agentSessions";
import { allAgentSessionPagesKey } from "@/lib/api/queryKeys";

import { prefetchAllAgentSessions } from "./useAllAgentSessions";

describe("prefetchAllAgentSessions", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("fills the default view's key with the first page, once while fresh", async () => {
    const listAll = vi
      .spyOn(agentSessionsApi, "listAll")
      .mockResolvedValue({ sessions: [], next_cursor: null, unavailable: [] } as never);
    const qc = new QueryClient();
    await prefetchAllAgentSessions(qc);
    await prefetchAllAgentSessions(qc);
    expect(listAll).toHaveBeenCalledTimes(1);
    expect(listAll.mock.calls[0][0]).toMatchObject({ q: "", limit: 30, cursor: null });
    expect(qc.getQueryData(allAgentSessionPagesKey("", { source: [], agent: [] }))).toBeDefined();
  });
});
