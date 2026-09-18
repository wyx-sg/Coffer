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
//
// Every key that names one resource is keyed on its UID, never on its name. A
// cache key has to identify the same row before and after a rename, and a name
// does not: keying on it would leave the renamed resource's entries stranded
// under the old label while its detail page mounted a fresh, empty one.
import type { QueryKey } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// resources — the generic /resources API (every kind)
// ---------------------------------------------------------------------------

export const resourcesKey = ["resources"] as const;
/** One kind's list (`kind` undefined = every kind). Object segment so a
 *  `["resources", { kind: "mcp_server" }]` invalidation matches by kind. */
export const resourcesByKindKey = (kind?: string) => ["resources", { kind }] as const;
/** One resource, by uid. The kind is NOT a segment: a uid already names
 *  exactly one row, and a second segment would only be a second way to get it
 *  wrong. */
export const resourceKey = (uid: string) => ["resources", uid] as const;

// ---------------------------------------------------------------------------
// agents
// ---------------------------------------------------------------------------

export const agentsKey = ["agents"] as const;
export const agentKey = (uid: string) => ["agents", uid] as const;
export const agentCandidatesKey = ["agents", "candidates"] as const;
export const agentConfigFilesKey = (uid: string) => ["agents", uid, "config-files"] as const;
export const agentConfigFileKey = (uid: string, key: string) =>
  ["agents", uid, "config-files", key] as const;
export const agentConfigChildKey = (uid: string, key: string, relpath: string) =>
  ["agents", uid, "config-files", key, relpath] as const;
export const agentMcpInstallKey = (uid: string) => ["agents", uid, "mcp-install"] as const;
export const agentMcpEntriesKey = (uid: string) => ["agents", uid, "mcp-entries"] as const;
export const agentPluginsKey = (uid: string) => ["agents", uid, "plugins"] as const;
export const agentUnmanagedSkillsKey = (uid: string) =>
  ["agents", uid, "unmanaged-skills"] as const;
export const agentNativeMemoryKey = (uid: string) => ["agents", uid, "native-memory"] as const;
/** One page of an agent's transcript list; `params` omitted = the whole
 *  subtree, for invalidation. */
export const agentTranscriptsKey = <P extends object>(uid: string, params?: P) =>
  params
    ? (["agents", uid, "conversations", params] as const)
    : (["agents", uid, "conversations"] as const);
/** One session's body, keyed by its FILE: `session_id` repeats across the
 *  sidechain files a single conversation can leave behind, so the path is the
 *  only thing that names exactly one of them. */
export const agentTranscriptSessionKey = (uid: string, sourcePath: string, offset: number) =>
  ["agents", uid, "conversations", "session", sourcePath, offset] as const;

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
export const skillKey = (uid: string) => ["skills", uid] as const;
export const skillFilesKey = (uid: string) => ["skills", uid, "files"] as const;
export const skillFileKey = (uid: string, path: string) =>
  ["skills", uid, "file", path] as const;

// ---------------------------------------------------------------------------
// mcp — per-server discovery, health and invocation log
// ---------------------------------------------------------------------------

export const mcpCapabilitiesKey = (serverUid: string) =>
  ["mcp", "capabilities", serverUid] as const;
export const mcpStatusKey = (serverUid: string) => ["mcp", "status", serverUid] as const;
export const mcpInvocationsKey = (serverUid: string, filters: Record<string, unknown>) =>
  ["mcp", "invocations", serverUid, filters] as const;
/** The gateway-wide invocation log (every server) — the Activity page. */
export const mcpAllInvocationsKey = (filters: Record<string, unknown>) =>
  ["mcp", "invocations", "all", filters] as const;

// ---------------------------------------------------------------------------
// providers (connections)
// ---------------------------------------------------------------------------

export const providersKey = ["providers"] as const;
export const providerKey = (uid: string) => ["providers", uid] as const;

/** The models a connection's endpoint reports. Deliberately NOT under
 *  `providerKey(uid)`: every connection mutation invalidates that subtree,
 *  and this list changes when the ENDPOINT changes, not when our curation
 *  does. MUST stay equal to `endpointModelsKey` in
 *  `lib/hooks/useModelIntrospection.ts` until that file imports this one. */
export const endpointModelsKey = (uid: string) => ["endpointModels", uid] as const;

// ---------------------------------------------------------------------------
// channels — channel resources ride `resourcesKey`; only live status is here
// ---------------------------------------------------------------------------

export const channelStatusKey = (uid: string) => ["channels", uid, "status"] as const;

// ---------------------------------------------------------------------------
// workflow — runs, their events/artifacts, and approvals across every run
// ---------------------------------------------------------------------------
//
// Templates are resources of kind `workflow` (FR-001) and live under
// `resourcesKey`, so nothing for them here. Everything else nests under the
// run it belongs to, so a node action can invalidate `workflowRunKey(id)` and
// sweep the run's detail, events and artifacts together.

export const workflowRunsKey = ["workflow", "runs"] as const;
/** The run list, narrowed by status. Object segment so a status-less
 *  invalidation of `workflowRunsKey` still catches every filtered list. */
export const workflowRunsListKey = (status?: string) => ["workflow", "runs", { status }] as const;
export const workflowRunKey = (runId: string) => ["workflow", "runs", runId] as const;
export const workflowArtifactsKey = (runId: string) =>
  ["workflow", "runs", runId, "artifacts"] as const;
/** What the run READS. Its own key because inputs are editable for the whole
 *  of a run's life (FR-050) and change without the run's position moving. */
export const workflowInputsKey = (runId: string) => ["workflow", "runs", runId, "inputs"] as const;
/** Approvals are their own subtree, not a child of a run: the page that
 *  decides one lists them across every run (FR-045). The root exists because
 *  a decision moves every filtered list at once. */
export const workflowApprovalsRootKey = ["workflow", "approvals"] as const;
export const workflowApprovalsKey = (filters: Record<string, unknown>) =>
  ["workflow", "approvals", filters] as const;

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
export const resourceScopeKey = (uid: string) => ["scope", uid] as const;

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
 *  browses (spec memory FR-037). */
export const memoryPartitionFilesKey = (partitionUid: string) =>
  ["memory", "partitions", partitionUid, "files"] as const;
export const memoryPartitionFileKey = (partitionUid: string, path: string) =>
  ["memory", "partitions", partitionUid, "files", "content", path] as const;
export const memoryDeliveryKey = ["memory", "delivery"] as const;
export const memoryAgentDeliveryKey = (agentUid: string) =>
  ["memory", "delivery", agentUid] as const;

// ---------------------------------------------------------------------------
// upkeep — the long rewrites (memory organise, knowledge curation) in flight
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
 * resource list — `useSkill` reads `skillKey(uid)`, `useProvider` reads
 * `providerKey(uid)`, agents read `agentKey(uid)`. Invalidating only
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
