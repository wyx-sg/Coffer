// frontend/src/lib/api/queryKeys.capabilities.ts — the Capabilities pages' query keys (skills, MCP servers, custom tools).
//
// Part of queryKeys.ts, split out only to keep that module under the file-size
// limit; it re-exports everything here, so callers import from queryKeys.ts
// and the rules written at its top apply unchanged.

// --- skills ----------------------------------------------------------------

export const skillsKey = ["skills"] as const;
export const skillFilesKey = (uid: string) => ["skills", uid, "files"] as const;
export const skillFileKey = (uid: string, path: string) => ["skills", uid, "file", path] as const;
/** One file's three versions in a staged update (local, pinned, incoming). */
/** The read-only drift report (Check copies): every agent's copy of every skill. */
export const skillCopiesKey = ["skills", "copies"] as const;
/** One agent's differing copy of a skill, compared with master. */
export const skillCopyKey = (uid: string, agentUid: string) =>
  ["skills", uid, "copies", agentUid] as const;
/** Folders in the skills store no skill claims ("Not in your library"). */
export const skillOrphansKey = ["skills", "orphans"] as const;
export const skillCompareKey = (uid: string, stagingId: string, path: string) =>
  ["skills", uid, "compare", stagingId, path] as const;

// --- mcp — per-server discovery, health and invocation log -----------------
/** The built-in `coffer` server; the dry-run plan of importing chosen agent entries. */
export const mcpBuiltinKey = ["mcp", "builtin"] as const;
export const mcpImportPlanKey = (e: readonly unknown[]) => ["agents", "mcp-import", e] as const;

export const mcpCapabilitiesKey = (serverUid: string) =>
  ["mcp", "capabilities", serverUid] as const;
/** Prefix of every server's status: a change to any MCP server refreshes them. */
export const mcpStatusesKey = ["mcp", "status"] as const;
export const mcpStatusKey = (serverUid: string) => [...mcpStatusesKey, serverUid] as const;
export const mcpInvocationsKey = (serverUid: string, filters: Record<string, unknown>) =>
  ["mcp", "invocations", serverUid, filters] as const;
/** The gateway-wide invocation log (every server) — the Activity page. */
export const mcpAllInvocationsKey = (filters: Record<string, unknown>) =>
  ["mcp", "invocations", "all", filters] as const;
/** The server page's reads: the last 24 hours, its own log, the tiering split. */
export const mcpSummaryKey = (serverUid: string) => ["mcp", "summary", serverUid] as const;
export const mcpLogKey = (serverUid: string) => ["mcp", "log", serverUid] as const;
export const mcpTieringKey = (serverUid: string) => ["mcp", "tiering", serverUid] as const;

// customTools — keyed on a group's NAME, fixed once made and its routes' only id.
export const customToolsKey = ["customTools"] as const;
export const customToolGroupKey = (name: string) => ["customTools", name] as const;
