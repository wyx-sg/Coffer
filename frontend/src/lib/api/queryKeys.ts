// frontend/src/lib/api/queryKeys.ts — every TanStack Query key the app uses.
//
// One module, flat named builders (`xKey` / `xKey(...)`), each returning an
// `as const` tuple. Keys are hierarchical: the first segment is the feature
// noun and a detail/sub-resource extends its parent, so a prefix invalidation
// (`qc.invalidateQueries({ queryKey: agentsKey })`) sweeps the whole subtree
// (.agents/frontend.md §3). Never inline a string-array `queryKey` at a call
// site — an ESLint rule (eslint.config.js) rejects it outside this file.
//
// A bare root (`["mcp"]`) is declared only where something actually invalidates
// through it. Every child spells its own segments out, so a feature whose
// writes are all narrow needs no root and does not get one for symmetry.
//
// Two keys keep a flat shape on purpose, documented where they are declared:
// `messagesKey` (a sibling of the conversation, not a child) and
// `endpointModelsKey` (deliberately NOT under `providersKey`).
import type { QueryKey } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// resources — the generic /resources API (every kind)
// ---------------------------------------------------------------------------

export const resourcesKey = ["resources"] as const;
/** One kind's list (`kind` undefined = every kind). Object segment so a
 *  `["resources", { kind: "mcp_server" }]` invalidation matches by kind. */
export const resourcesByKindKey = (kind?: string) => ["resources", { kind }] as const;
export const resourceKey = (kind: string, name: string) => ["resources", kind, name] as const;

// ---------------------------------------------------------------------------
// agents
// ---------------------------------------------------------------------------

export const agentsKey = ["agents"] as const;
export const agentKey = (name: string) => ["agents", name] as const;
export const agentCandidatesKey = ["agents", "candidates"] as const;
export const agentConfigFilesKey = (name: string) => ["agents", name, "config-files"] as const;
export const agentConfigFileKey = (name: string, key: string) =>
  ["agents", name, "config-files", key] as const;
export const agentConfigChildKey = (name: string, key: string, relpath: string) =>
  ["agents", name, "config-files", key, relpath] as const;
export const agentMcpInstallKey = (name: string) => ["agents", name, "mcp-install"] as const;
export const agentMcpEntriesKey = (name: string) => ["agents", name, "mcp-entries"] as const;
export const agentPluginsKey = (name: string) => ["agents", name, "plugins"] as const;
export const agentUnmanagedSkillsKey = (name: string) =>
  ["agents", name, "unmanaged-skills"] as const;
export const agentNativeMemoryKey = (name: string) => ["agents", name, "native-memory"] as const;
/** One page of an agent's transcript list; `params` omitted = the whole
 *  subtree, for invalidation. */
export const agentTranscriptsKey = <P extends object>(name: string, params?: P) =>
  params
    ? (["agents", name, "conversations", params] as const)
    : (["agents", name, "conversations"] as const);
/** One session's body, keyed by its FILE: `session_id` repeats across the
 *  sidechain files a single conversation can leave behind, so the path is the
 *  only thing that names exactly one of them. */
export const agentTranscriptSessionKey = (name: string, sourcePath: string, offset: number) =>
  ["agents", name, "conversations", "session", sourcePath, offset] as const;

// ---------------------------------------------------------------------------
// agentProviders — the turn platform's agent registry (/agent-providers)
// ---------------------------------------------------------------------------

export const agentProvidersKey = ["agentProviders"] as const;
/** An agent's model catalogue (/agent-providers/{key}/models), keyed by the
 *  provider key (`claude_code`, …), not a registry name. */
export const agentProviderModelsKey = (agentKey: string) =>
  ["agentProviders", agentKey, "models"] as const;

// ---------------------------------------------------------------------------
// skills
// ---------------------------------------------------------------------------

export const skillsKey = ["skills"] as const;
export const skillKey = (name: string) => ["skills", name] as const;
export const skillFilesKey = (name: string) => ["skills", name, "files"] as const;
export const skillFileKey = (name: string, path: string) => ["skills", name, "file", path] as const;

// ---------------------------------------------------------------------------
// mcp — per-server discovery, health and invocation log
// ---------------------------------------------------------------------------

export const mcpCapabilitiesKey = (serverName: string) =>
  ["mcp", "capabilities", serverName] as const;
export const mcpStatusKey = (serverName: string) => ["mcp", "status", serverName] as const;
export const mcpInvocationsKey = (serverName: string, filters: Record<string, unknown>) =>
  ["mcp", "invocations", serverName, filters] as const;
/** The gateway-wide invocation log (every server) — the Activity page. */
export const mcpAllInvocationsKey = (filters: Record<string, unknown>) =>
  ["mcp", "invocations", "all", filters] as const;

// ---------------------------------------------------------------------------
// providers (connections)
// ---------------------------------------------------------------------------

export const providersKey = ["providers"] as const;
export const providerKey = (name: string) => ["providers", name] as const;

/** The models a connection's endpoint reports. Deliberately NOT under
 *  `providerKey(name)`: every connection mutation invalidates that subtree,
 *  and this list changes when the ENDPOINT changes, not when our curation
 *  does. MUST stay equal to `endpointModelsKey` in
 *  `lib/hooks/useModelIntrospection.ts` until that file imports this one. */
export const endpointModelsKey = (name: string) => ["endpointModels", name] as const;

// ---------------------------------------------------------------------------
// channels — channel resources ride `resourcesKey`; only live status is here
// ---------------------------------------------------------------------------

export const channelStatusKey = (name: string) => ["channels", name, "status"] as const;

// ---------------------------------------------------------------------------
// daemon
// ---------------------------------------------------------------------------

export const daemonStatusKey = ["daemon", "status"] as const;
export const daemonLogsKey = (filters: Record<string, unknown>) =>
  ["daemon", "logs", filters] as const;
export const daemonVersionSkewKey = (version: string | undefined) =>
  ["daemon", "version-skew", version] as const;

// ---------------------------------------------------------------------------
// fs — the loopback daemon's view of the local filesystem
// ---------------------------------------------------------------------------

export const fsBrowseKey = (path: string) => ["fs", "browse", path] as const;
export const fsEditorsKey = ["fs", "editors"] as const;

// ---------------------------------------------------------------------------
// audit / retention
// ---------------------------------------------------------------------------

export const auditListKey = (filters: Record<string, unknown>) => ["audit", filters] as const;

export const retentionKey = ["retention"] as const;
export const retentionPoliciesKey = ["retention", "policies"] as const;

// ---------------------------------------------------------------------------
// sync — rounds, machine registry, master key
// ---------------------------------------------------------------------------

export const syncKey = ["sync"] as const;
export const syncStatusKey = ["sync", "status"] as const;
export const syncMachinesKey = ["sync", "machines"] as const;
export const syncRunsKey = ["sync", "runs"] as const;
export const syncKeyFingerprintKey = ["sync", "key-fingerprint"] as const;

// ---------------------------------------------------------------------------
// scope — per-agent activation scope of one resource
// ---------------------------------------------------------------------------

export const scopeKey = ["scope"] as const;
export const resourceScopeKey = (kind: string, name: string) => ["scope", kind, name] as const;

// ---------------------------------------------------------------------------
// knowledge — collections, one directory level per key, one file per key
// ---------------------------------------------------------------------------

export const knowledgeKey = ["knowledge"] as const;
export const knowledgeCollectionsKey = ["knowledge", "collections"] as const;
/** One directory level; `path` is relative to the knowledge root. */
export const knowledgeTreeKey = (path: string) => ["knowledge", "tree", path] as const;
export const knowledgeFileKey = (path: string) => ["knowledge", "file", path] as const;

// ---------------------------------------------------------------------------
// memory — partitions, files, delivery
// ---------------------------------------------------------------------------

export const memoryKey = ["memory"] as const;
export const memoryPartitionsKey = ["memory", "partitions"] as const;
/** A partition's own directory, and one file in it — the tree the detail page
 *  browses (spec memory FR-029). */
export const memoryPartitionFilesKey = (partition: string) =>
  ["memory", "partitions", partition, "files"] as const;
export const memoryPartitionFileKey = (partition: string, path: string) =>
  ["memory", "partitions", partition, "files", "content", path] as const;
export const memoryDeliveryKey = ["memory", "delivery"] as const;
export const memoryAgentDeliveryKey = (agent: string) => ["memory", "delivery", agent] as const;

// ---------------------------------------------------------------------------
// upkeep — the long rewrites (memory organise, knowledge tidy) in flight
// ---------------------------------------------------------------------------

/** Deliberately NOT under `memoryKey` or `knowledgeKey`: one read answers for
 *  every kind, and a pass ending must not drag either kind's whole subtree
 *  into the same invalidation. */
export const upkeepRunsKey = ["upkeep", "runs"] as const;

// ---------------------------------------------------------------------------
// chat — conversations, their messages and per-conversation agent config
// ---------------------------------------------------------------------------

export const conversationsKey = ["conversations"] as const;
export const archivedConversationsKey = ["conversations", "archived"] as const;
export const conversationKey = (id: string) => ["conversations", id] as const;
/** A conversation's managed-agent config (model, effort). A CHILD of the
 *  conversation, so removing `conversationKey(id)` drops it too. */
export const agentConfigKey = (conversationId: string) =>
  ["conversations", conversationId, "agentConfig"] as const;
/** A conversation's messages. A SIBLING of `conversationKey`, not a child:
 *  every rename/archive/create invalidates `conversationsKey`, and a child
 *  key would make each of those refetch an open thread — mid-stream, that
 *  would clobber the partial the turn hooks are writing into this key. */
export const messagesKey = (conversationId: string) => ["messages", conversationId] as const;

// ---------------------------------------------------------------------------
// settings — daemon-side settings the Settings pages edit
// ---------------------------------------------------------------------------

export const credentialSettingsKey = ["settings", "credentials"] as const;
export const internalEngineKey = ["settings", "internalEngine"] as const;

// ---------------------------------------------------------------------------
// cross-kind helpers
// ---------------------------------------------------------------------------

/**
 * Some kinds are read through their OWN list key rather than the generic
 * resource list — `useSkill` reads `skillKey(name)`, `useProvider` reads
 * `providerKey(name)`, agents read `agentKey(name)`. Invalidating only
 * `resourcesKey` leaves those surfaces rendering the pre-write state (a skill
 * detail page would keep showing "enabled" after a successful disable), so a
 * kind-agnostic write (enable/disable/delete/scope) refreshes this key too.
 * Undefined for kinds that only live under `resourcesKey`.
 */
export function ownListKeyForKind(kind: string): QueryKey | undefined {
  switch (kind) {
    case "skill":
      return skillsKey;
    case "provider":
      return providersKey;
    case "agent":
      return agentsKey;
    default:
      return undefined;
  }
}
