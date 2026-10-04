// src/components/mcp/server/testResult.ts — what one test of a registered server found, as the pane reads it.
import type { components } from "@/lib/api/types";

export type TestResult = components["schemas"]["McpTestResultOut"];

/** The pane's view of a test that could not even be asked (a transport error). */
export function failedTest(message: string): TestResult {
  return {
    ok: false,
    latency_ms: 0,
    error_message: message,
    error_code: null,
    exit_code: null,
    protocol_version: null,
    server_capabilities: null,
    prompt_count: null,
    resource_count: null,
    stderr_tail: [],
    tool_count: 0,
    tools: [],
    unreleased_secret_keys: [],
    handoff: null,
  };
}
