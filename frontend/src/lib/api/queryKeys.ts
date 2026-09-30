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

// --- resources — the generic /resources API (every kind) -------------------

export const resourcesKey = ["resources"] as const;
/** One kind's list (`kind` undefined = every kind). Object segment so a
 *  `["resources", { kind: "mcp_server" }]` invalidation matches by kind. */
export const resourcesByKindKey = (kind?: string) => ["resources", { kind }] as const;
/** One resource, by uid. The kind is NOT a segment: a uid already names
 *  exactly one row, and a second segment would only be a second way to get it
 *  wrong. */
export const resourceKey = (uid: string) => ["resources", uid] as const;

// --- agents ----------------------------------------------------------------

export const agentsKey = ["agents"] as const;
export const agentKey = (uid: string) => ["agents", uid] as const;
/** One row per supported type, registered or not (`GET /agents/types`). */
export const agentTypesKey = ["agents", "types"] as const;
export const agentConfigFilesKey = (uid: string) => ["agents", uid, "config-files"] as const;
export const agentConfigFileKey = (uid: string, key: string) =>
  ["agents", uid, "config-files", key] as const;
export const agentConfigChildKey = (uid: string, key: string, relpath: string) =>
  ["agents", uid, "config-files", key, relpath] as const;
export const agentConnectionKey = (uid: string) => ["agents", uid, "coffer-connection"] as const;
export const agentMcpEntriesKey = (uid: string) => ["agents", uid, "mcp-entries"] as const;
/** One entry's detail — under the listing's key, so whatever refreshes the
 *  listing (a remove, an adopt) refreshes the detail too. */
export const agentMcpEntryKey = (uid: string, entry: string, source: string) =>
  ["agents", uid, "mcp-entries", entry, source] as const;
export const agentHooksKey = (uid: string) => ["agents", uid, "hooks"] as const;
export const agentPluginsKey = (uid: string) => ["agents", uid, "plugins"] as const;
/** One plugin's detail — under the listing's key, so a toggle or uninstall that
 *  invalidates the listing refreshes the detail page too. */
export const agentPluginKey = (uid: string, id: string) => ["agents", uid, "plugins", id] as const;
export const agentUnmanagedSkillsKey = (uid: string) =>
  ["agents", uid, "unmanaged-skills"] as const;
/** One unmanaged folder's preview — nested under the list key, so adopting or
 *  deleting (which invalidate the list) also drops the preview. */
export const agentUnmanagedSkillKey = (uid: string, location: string, name: string) =>
  ["agents", uid, "unmanaged-skills", location, name] as const;
export const agentUnmanagedSkillFilesKey = (uid: string, location: string, name: string) =>
  ["agents", uid, "unmanaged-skills", location, name, "files"] as const;
export const agentUnmanagedSkillFileKey = (
  uid: string,
  location: string,
  name: string,
  path: string,
) => ["agents", uid, "unmanaged-skills", location, name, "file", path] as const;
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

// --- agentProviders — the turn platform's agent registry (/agent-providers) ---

export const agentProvidersKey = ["agentProviders"] as const;
/** An agent's model catalogue (/agent-providers/{key}/models), keyed by the
 *  provider key (`claude_code`, …), not a registry name. */
export const agentProviderModelsKey = (agentKey: string) =>
  ["agentProviders", agentKey, "models"] as const;

// --- skills ----------------------------------------------------------------

export const skillsKey = ["skills"] as const;
export const skillFilesKey = (uid: string) => ["skills", uid, "files"] as const;
export const skillFileKey = (uid: string, path: string) => ["skills", uid, "file", path] as const;
/** One file's three versions in a staged update (local, pinned, incoming). */
export const skillCompareKey = (uid: string, stagingId: string, path: string) =>
  ["skills", uid, "compare", stagingId, path] as const;

// vault history: any vault file or folder, e.g. a skill's `skills/<name>/`
export const vaultKey = ["vault"] as const;
export const vaultHistoryKey = (path: string) => ["vault", "history", path] as const;
export const vaultDiffKey = (path: string, v: string) => ["vault", "diff", path, v] as const;

// --- mcp — per-server discovery, health and invocation log -----------------

export const mcpCapabilitiesKey = (serverUid: string) =>
  ["mcp", "capabilities", serverUid] as const;
/** Prefix of every server's status: a change to any MCP server refreshes them. */
const mcpStatusesKey = ["mcp", "status"] as const;
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

// --- attention — the cross-kind "needs you" list the Overview shows --------

/** GET /attention. A `change` event of kind `attention` invalidates it. */
export const attentionKey = ["attention"] as const;

// --- providers (connections) -----------------------------------------------

export const providersKey = ["providers"] as const;
export const providerKey = (uid: string) => ["providers", uid] as const;

/** The models a connection's endpoint reports. NOT under `providerKey(uid)`:
 *  it changes with the ENDPOINT, not with every connection mutation. */
export const endpointModelsKey = (uid: string) => ["endpointModels", uid] as const;

/** POST /providers/detect-local at a loopback URL (`null` = default ports); a runtime, not a connection. */
export const localRuntimesKey = (baseUrl: string | null) => ["localRuntimes", baseUrl] as const;
// usage — GET /usage/summary per range + grouping, GET /usage/quota
export const usageKey = ["usage"] as const;
export const usageSummaryKey = (p: Record<string, unknown>) => ["usage", "summary", p] as const;
export const usageQuotaKey = ["usage", "quota"] as const;

// --- channels — channel resources ride `resourcesKey`; only live status is here ---

/** Prefix of every channel status key: a title or rename refreshes them all. */
const channelsKey = ["channels"] as const;
export const channelStatusKey = (uid: string) => ["channels", uid, "status"] as const;

// --- daemon ----------------------------------------------------------------

export const daemonStatusKey = ["daemon", "status"] as const;
export const daemonLogsKey = (filters: Record<string, unknown>) =>
  ["daemon", "logs", filters] as const;
export const daemonVersionSkewKey = (version: string | undefined) =>
  ["daemon", "version-skew", version] as const;
export const daemonResidencyKey = ["daemon", "residency"] as const;
export const daemonPortKey = ["daemon", "port"] as const;
/** Settings > Data: what Coffer keeps on this machine, by kind. */
export const storageKey = ["storage"] as const;
export const daemonFeaturesKey = ["daemon", "features"] as const;

// --- fs — the loopback daemon's view of the local filesystem ---------------

export const fsBrowseKey = (path: string) => ["fs", "browse", path] as const;
export const fsEditorsKey = ["fs", "editors"] as const;

// --- audit / retention -----------------------------------------------------

export const auditListKey = (filters: Record<string, unknown>) => ["audit", filters] as const;

export const retentionKey = ["retention"] as const;
export const retentionPoliciesKey = ["retention", "policies"] as const;

// --- sync — rounds, machine registry, master key ---------------------------

export const syncKey = ["sync"] as const;
export const syncStatusKey = ["sync", "status"] as const;
export const syncMachinesKey = ["sync", "machines"] as const;
export const syncRunsKey = ["sync", "runs"] as const;
export const syncKeyFingerprintKey = ["sync", "key-fingerprint"] as const;

// --- scope — per-agent activation scope of one resource --------------------

export const scopeKey = ["scope"] as const;
export const resourceScopeKey = (uid: string) => ["scope", uid] as const;

// --- knowledge — collections, tree levels, files, changes, document history ---

export const knowledgeKey = ["knowledge"] as const;
export const knowledgeCollectionsKey = ["knowledge", "collections"] as const;
export const knowledgeTreeRootKey = ["knowledge", "tree"] as const;
export const knowledgeTreeKey = (path: string) => ["knowledge", "tree", path] as const;
export const knowledgeFileKey = (path: string) => ["knowledge", "file", path] as const;
export const knowledgeChangesRootKey = ["knowledge", "changes"] as const;
export const knowledgeChangesKey = (collection: string | null) =>
  ["knowledge", "changes", "list", collection ?? ""] as const;
export const knowledgeChangeKey = (version: string) =>
  ["knowledge", "changes", "detail", version] as const;
export const knowledgeHistoryKey = (path: string) => ["knowledge", "history", path] as const;
export const knowledgeVersionDiffKey = (path: string, version: string) =>
  ["knowledge", "history", path, "diff", version] as const;

// --- memory — partitions, their memories, what is delivered ---------------

export const memoryKey = ["memory"] as const;
export const memoryPartitionsKey = ["memory", "partitions"] as const;
export const memoryPartitionFilesKey = (uid: string) =>
  ["memory", "partitions", uid, "files"] as const;
export const memoryNotesKey = (uid: string) => ["memory", "partitions", uid, "notes"] as const;
export const memoryNoteKey = (uid: string, slug: string) =>
  ["memory", "partitions", uid, "notes", slug] as const;
export const memoryRetiredKey = (uid: string) => ["memory", "partitions", uid, "retired"] as const;
export const memoryDeliveredKey = (uid: string) =>
  ["memory", "partitions", uid, "delivered"] as const;
export const memoryDeliveriesKey = ["memory", "deliveries"] as const;

// --- upkeep — the long rewrites (memory organise, knowledge curation) in flight ---

/** Deliberately NOT under `memoryKey` or `knowledgeKey`: one read answers for
 *  every kind, and a pass ending must not drag either kind's whole subtree
 *  into the same invalidation. */
export const upkeepRunsKey = ["upkeep", "runs"] as const;

// --- chat — conversations, their messages and per-conversation agent config ---

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

// --- credentials — the secret boundary's approvals -------------------------

export const credentialsKey = ["credentials"] as const;
/** The approvals still waiting for a present human. */
export const pendingApprovalsKey = ["credentials", "approvals", "pending"] as const;
export const secretBoundaryKey = ["credentials", "secret-boundary"] as const;
export const credentialsListKey = ["credentials", "list"] as const;
export const credentialScanKey = ["credentials", "scan"] as const;

// customTools — keyed on a group's NAME, fixed once made and its routes' only id.
export const customToolsKey = ["customTools"] as const;
export const customToolGroupKey = (name: string) => ["customTools", name] as const;

// ---------------------------------------------------------------------------
// clis — the commands managed skills require (/clis)
// ---------------------------------------------------------------------------

export const clisKey = ["clis"] as const;
/** One command. Keyed on the command itself: it is the row's only identity,
 *  and no rename exists that could strand the entry. */
export const cliKey = (command: string) => ["clis", command] as const;

// --- settings — daemon-side settings the Settings pages edit ---------------

export const credentialSettingsKey = ["settings", "credentials"] as const;
export const internalEngineKey = ["settings", "internalEngine"] as const;

// --- cross-kind helpers ----------------------------------------------------

/**
 * Some kinds are read through their OWN list keys rather than the generic
 * resource list — the Skills page reads `skillsKey`, `useProvider` reads
 * `providerKey(uid)`, agents read `agentKey(uid)`. Invalidating only
 * `resourcesKey` leaves those surfaces rendering the pre-write state (a skill
 * detail page would keep showing "enabled" after a successful disable), so a
 * kind-agnostic write (enable/disable/delete/scope) refreshes these keys too.
 * An `mcp_server` has two readers: the MCP servers page's statuses and the
 * Custom tools page, whose groups are `mcp_server`s too. Empty for kinds that
 * only live under `resourcesKey`.
 */
export function ownListKeysForKind(kind: string): readonly QueryKey[] {
  switch (kind) {
    case "skill":
      return [skillsKey];
    case "provider":
      return [providersKey];
    case "agent":
      return [agentsKey];
    case "knowledge":
      return [knowledgeCollectionsKey];
    case "memory":
      return [memoryPartitionsKey];
    case "channel":
      return [channelsKey];
    case "mcp_server":
      return [mcpStatusesKey, customToolsKey];
    default:
      return [];
  }
}
