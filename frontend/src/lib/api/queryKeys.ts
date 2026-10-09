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
// One key keeps a flat shape on purpose, documented where it is declared:
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
export const agentConfigFileContentKey = (uid: string, key: string, child: string) =>
  ["agents", uid, "config-files", key, child] as const;
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
/** An agent's native sessions: `q` omitted = the whole subtree, for invalidation. */
export const agentSessionsKey = (uid: string, q?: string) =>
  q === undefined
    ? (["agents", uid, "sessions"] as const)
    : (["agents", uid, "sessions", { q }] as const);

// --- agentProviders — the turn platform's agent registry (/agent-providers) ---

export const agentProvidersKey = ["agentProviders"] as const;
/** An agent's model catalogue (/agent-providers/{key}/models), keyed by the
 *  provider key (`claude_code`, …), not a registry name. */
export const agentProviderModelsKey = (agentKey: string) =>
  ["agentProviders", agentKey, "models"] as const;
/** The same catalogue for the agent's own login, whatever it runs on now. */
export const agentBuiltinModelsKey = (agentKey: string) =>
  ["agentProviders", agentKey, "models", "builtin"] as const;

// --- skills, mcp, customTools — in queryKeys.capabilities.ts ---------------
export * from "./queryKeys.capabilities";
import { customToolsKey, mcpStatusesKey, skillsKey } from "./queryKeys.capabilities";

// vault history: any vault file or folder, e.g. a skill's `skills/<name>/` or a
// knowledge document's `knowledge/<collection>/<file>`
export const vaultKey = ["vault"] as const;
export const vaultHistoryKey = (path: string) => [...vaultKey, "history", path] as const;
export const vaultDiffKey = (path: string, version: string, against: string) =>
  [...vaultKey, "diff", path, version, against] as const;

// --- attention — the cross-kind "needs you" list the Overview shows --------

/** GET /attention. A `change` event of kind `attention` invalidates it. */
export const attentionKey = ["attention"] as const;

// --- providers (connections) -----------------------------------------------

export const providersKey = ["providers"] as const;
export const providerKey = (uid: string) => ["providers", uid] as const;
/** GET /providers/health — under `providersKey`, so a `provider` change refetches it. */
export const providerHealthKey = ["providers", "health"] as const;

/** The models a connection's endpoint reports. NOT under `providerKey(uid)`:
 *  it changes with the ENDPOINT, not with every connection mutation. */
export const endpointModelsKey = (uid: string) => ["endpointModels", uid] as const;

/** Model prices: under `providerKey(uid)` (a PATCH refetches); `listedAt` refetches after a listing. */
export const providerPricesKey = (uid: string, models: readonly string[], listedAt: number) =>
  ["providers", uid, "prices", models, listedAt] as const;

// The model proxy's query keys live beside its api, in lib/api/proxy.ts.

/** POST /providers/detect-local at a loopback URL (`null` = default ports); a runtime, not a connection. */
export const localRuntimesKey = (baseUrl: string | null) => ["localRuntimes", baseUrl] as const;
// usage — GET /usage/summary per range + grouping
export const usageSummaryKey = (p: Record<string, unknown>) => ["usage", "summary", p] as const;

// --- channels — channel resources ride `resourcesKey`; only live status is here ---

/** Prefix of every channel status key: a title or rename refreshes them all. */
const channelsKey = ["channels"] as const;
export const channelStatusKey = (uid: string) => ["channels", uid, "status"] as const;
/** A paired person's picture, as a `data:` URL or `null` (show initials). */
export const channelAvatarKey = (uid: string, senderId: string) =>
  ["channels", uid, "avatar", senderId] as const;

// --- daemon ----------------------------------------------------------------

export const daemonStatusKey = ["daemon", "status"] as const;
export const daemonLogsKey = (filters: Record<string, unknown>) =>
  ["daemon", "logs", filters] as const;
export const daemonVersionSkewKey = (version: string | undefined) =>
  ["daemon", "version-skew", version] as const;
export const daemonResidencyKey = ["daemon", "residency"] as const;
export const daemonPortKey = ["daemon", "port"] as const;
/** Settings › About in a browser: the prompt that upgrades Coffer. */
export const daemonUpgradeKey = ["daemon", "upgrade"] as const;
/** Settings > Data: what Coffer keeps on this machine, by kind. */
export const storageKey = ["storage"] as const;
export const daemonFeaturesKey = ["daemon", "features"] as const;

// --- fs — the loopback daemon's view of the local filesystem ---------------

export const fsBrowseKey = (path: string) => ["fs", "browse", path] as const;
export const fsEditorsKey = ["fs", "editors"] as const;
export const fsTerminalsKey = ["fs", "terminals"] as const;

// --- audit / retention -----------------------------------------------------

export const auditListKey = (filters: Record<string, unknown>) => ["audit", filters] as const;
/** Whether any of the three Activity logs holds a record (the first-run check). */
export const activityAnyRecordsKey = ["activity", "any-records"] as const;
/** One tool call with its recorded content (the call drawer). */
export const activityCallKey = (id: number) => ["activity", "call", id] as const;

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

// --- knowledge — collections, tree levels, files -----------------------------

export const knowledgeKey = ["knowledge"] as const;
export const knowledgeCollectionsKey = ["knowledge", "collections"] as const;
export const knowledgeTreeKey = (path: string) => ["knowledge", "tree", path] as const;
export const knowledgeFileKey = (path: string) => ["knowledge", "file", path] as const;

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
export const memoryReadingKey = ["memory", "reading"] as const;

// --- upkeep — the long rewrites (memory update) in flight ---

/** Deliberately NOT under `memoryKey`: one read answers for every kind, and a
 *  pass ending must not drag a kind's whole subtree into the same invalidation. */
export const upkeepRunsKey = ["upkeep", "runs"] as const;

// --- agent sessions — every agent's sessions in one list (the Conversations page) ---

export const allAgentSessionsKey = ["agent-sessions"] as const;

/** The pages the cross-agent list has read so far, for one view (search text, sources, agents). */
export const allAgentSessionPagesKey = (
  q: string,
  { source = [], agent = [] }: { source?: readonly string[]; agent?: readonly string[] } = {},
) =>
  ["agent-sessions", "pages", { q, source: [...source].sort(), agent: [...agent].sort() }] as const;

// --- secrets — the secret boundary's approvals -------------------------
export const secretsKey = ["secrets"] as const;
export const secretScanKey = [...secretsKey, "scan"] as const;
/** The approvals still waiting for a present human. */
export const pendingApprovalsKey = ["secrets", "approvals", "pending"] as const;
export const secretBoundaryKey = ["secrets", "secret-boundary"] as const;
export const secretsListKey = ["secrets", "list"] as const;

// --- settings — daemon-side settings the Settings pages edit ---------------

export const secretSettingsKey = ["settings", "secrets"] as const;
export const internalEngineKey = ["settings", "internalEngine"] as const;
/** Whether tool calls record their content (Settings › Data › History). */
export const callContentSettingKey = ["settings", "callContent"] as const;

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
