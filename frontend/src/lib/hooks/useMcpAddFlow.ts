// frontend/src/lib/hooks/useMcpAddFlow.ts — the MCP servers page's reads and
// writes beside the registered servers: test a config before Add server, plan
// an import from the agents (the first-run card shows the files it names), and
// Coffer's own built-in `coffer` server (change align-capabilities-with-final-design).
//
// None of these toast: the Add dialog renders a test result where the person
// acted, and a toast would repeat it.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef } from "react";

import { mcpBuiltinApi } from "@/lib/api/mcpBuiltin";
import { mcpImportApi, type McpImportEntryIn } from "@/lib/api/mcpImport";
import { mcpTestConfigApi, type McpConfigTestIn } from "@/lib/api/mcpTestConfig";
import { mcpBuiltinKey, mcpImportPlanKey } from "@/lib/api/queryKeys";

/**
 * Test a config that is not saved (`POST /resources/mcp_server/test-config`).
 * `mutate(body)` resolves with the result — a failed test resolves too, with
 * `ok: false` and an `error_code`. `cancel()` aborts the request, which stops
 * the daemon's test (it watches for the client going away).
 */
export function useMcpConfigTest() {
  const controller = useRef<AbortController | null>(null);
  const mutation = useMutation({
    mutationFn: (body: McpConfigTestIn) => {
      controller.current?.abort();
      const next = new AbortController();
      controller.current = next;
      return mcpTestConfigApi.test(body, next.signal);
    },
  });
  return {
    ...mutation,
    cancel: () => {
      controller.current?.abort();
      controller.current = null;
      mutation.reset();
    },
  };
}

/** The dry-run plan of importing `entries`; read while the first-run card shows it. */
export function useMcpImportPlan(entries: McpImportEntryIn[], enabled = true) {
  return useQuery({
    queryKey: mcpImportPlanKey(entries),
    enabled: enabled && entries.length > 0,
    queryFn: () => mcpImportApi.plan(entries),
    // A plan is a snapshot of files that may change under it: read it fresh.
    staleTime: 0,
    retry: false,
  });
}

/** Coffer's own `coffer` server: endpoint, tools, reach and the last 24 hours. */
export function useBuiltinMcpServer() {
  return useQuery({ queryKey: mcpBuiltinKey, queryFn: mcpBuiltinApi.get });
}
