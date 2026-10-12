// frontend/src/lib/activity/auditBuilders.ts
//
// The longer sentence builders for audit rows — memory, providers, resources,
// retention, skills, sync and tool exposure — split out of auditSentence.ts,
// which maps each event to its builder.

import { type Builder, Facts, agentLabel, countOf, joinNames, shortCommit } from "./auditFacts";

/** The memories a sync published or changed, else the copies it wrote. */
function memoryCount(f: Facts, kinds: readonly string[]): number {
  const hub = f.obj("hub");
  const published = hub ? kinds.reduce((n, k) => n + countOf(hub, k), 0) : 0;
  if (published) return published;
  const copies = f.obj("copies");
  if (!copies) return 0;
  return Object.keys(copies.raw).reduce((n, agent) => {
    const c = copies.obj(agent);
    return n + (c ? countOf(c, "written") + countOf(c, "updated") + countOf(c, "removed") : 0);
  }, 0);
}

export const memorySynced: Builder = (f) => {
  const count = memoryCount(f, ["created", "updated", "deleted"]);
  return count ? { v: "count", p: { count } } : null;
};

export const memorySyncUndone: Builder = (f) => {
  const copies = f.obj("copies");
  const count = copies
    ? Object.keys(copies.raw).reduce(
        (n, a) => n + countOf(copies.obj(a) ?? new Facts({}), "removed"),
        0,
      )
    : 0;
  return count ? { v: "count", p: { count } } : null;
};

export const projectionRefused: Builder = (f, { resource }) => {
  const agent = agentLabel(f.str("agent_type"));
  if (!agent) return null;
  return resource ? { v: "agent", p: { agent } } : { v: "noConnection", p: { agent } };
};

export const projectionRepaired: Builder = (f, { resource }) => {
  const agent = agentLabel(f.str("agent"));
  const connection = f.str("connection") || resource;
  const action = f.str("action");
  if (!agent) return null;
  if (action === "deproject") return { v: "deproject", p: { agent } };
  if (!connection) return null;
  return { v: action === "clear_connection" ? "clear" : "project", p: { agent, connection } };
};

export const providerSwitched: Builder = (f, { resource }) => {
  const agent = agentLabel(f.str("agent_type"));
  if (!agent) return null;
  if (f.has("to") && !f.str("to")) return { v: "off", p: { agent } };
  const to = resource || f.str("to");
  if (!to) return null;
  const from = f.str("from");
  return from && from !== to
    ? { v: "agentFrom", p: { agent, from, resource: to } }
    : { v: "agent", p: { agent, resource: to } };
};

export const resourceRenamed: Builder = (f, { resource }) => {
  const from = f.str("from");
  const to = resource || f.str("to");
  return from && to ? { v: "from", p: { from, resource: to } } : null;
};

export const scopeUpdated: Builder = (f, { t, resource }) => {
  if (!resource || !f.has("agents")) return null;
  const agents = f.list("agents");
  if (agents === null) return { v: "all" };
  const names = agents.filter((a): a is string => typeof a === "string").map(agentLabel);
  return names.length ? { v: "agents", p: { agents: joinNames(t, names) } } : { v: "none" };
};

export const retentionUpdated: Builder = (f, { t }) => {
  const table = f.str("table");
  if (!table || !f.has("retention_days")) return null;
  const days = (k: string) => {
    const n = f.num(k);
    return n === null
      ? t("audit.activity.retention_updated_forever")
      : t("audit.activity.retention_updated_days", { count: n });
  };
  const name = t(`settings.retention.policy.${table}.name`, { defaultValue: table });
  return f.has("previous_days")
    ? { v: "change", p: { table: name, from: days("previous_days"), to: days("retention_days") } }
    : { v: "to", p: { table: name, to: days("retention_days") } };
};

export const onOff =
  (key: string): Builder =>
  (f) => {
    const on = f.bool(key);
    return on === null ? null : { v: on ? "on" : "off" };
  };

export const skillUpdated: Builder = (f) => {
  const from = shortCommit(f.str("from_commit"));
  const to = shortCommit(f.str("to_commit"));
  if (from && to) return { v: "commits", p: { from, to } };
  if (f.bool("builtin")) return { v: "builtin" };
  return null;
};

export const skillUnmanagedDeleted: Builder = (f, { resource }) => {
  const name = f.str("name") || resource;
  if (!name) return null;
  const agent = agentLabel(f.str("agent"));
  return agent ? { v: "nameAgent", p: { name, agent } } : { v: "name", p: { name } };
};

/** The outcome of a sync round, by its status, with the files it moved. */
const SYNC_FAILURES: Record<string, string> = {
  stopped: "stopped",
  held: "held",
  waiting_on_edit: "waitingOnEdit",
  join_required: "joinRequired",
  unreachable: "unreachable",
  auth_failed: "authFailed",
  paused_cloud_folder: "pausedCloudFolder",
  remote_too_new: "remoteTooNew",
  plaintext_found: "plaintextFound",
  failed: "failed",
  push_failed: "pushFailed",
};

export const syncRun: Builder = (f) => {
  const status = f.str("status");
  const pulled = f.num("pulled") ?? 0;
  const pushed = f.num("pushed") ?? 0;
  if (status === "stopped" && f.num("conflicts"))
    return { v: "conflicts", p: { count: f.num("conflicts") } };
  if (status === "held" && f.num("held")) return { v: "heldCount", p: { count: f.num("held") } };
  if (status === "push_failed" && pulled) return { v: "pushFailedPulled", p: { count: pulled } };
  if (SYNC_FAILURES[status]) return { v: SYNC_FAILURES[status] };
  if (!status && !f.has("pulled") && !f.has("pushed")) return null;
  const joined = status === "joined" ? "joined" : "";
  if (pulled && pushed) return { v: `${joined}both`, p: { count: pulled, pushed } };
  if (pulled) return { v: `${joined}pulled`, p: { count: pulled } };
  if (pushed) return { v: `${joined}pushed`, p: { count: pushed } };
  return { v: joined || "nothing" };
};

export const toolExposure: Builder = (f, { t, resource }) => {
  const mode = f.str("mode");
  if (!resource) return null;
  const tools = f.list("tools") ?? [];
  const key =
    tools.length > 1
      ? t("audit.activity.tool_exposure_changed_tools", { count: tools.length })
      : f.str("key");
  if (!key) return null;
  if (!mode || mode === "mixed") return { v: "key", p: { key } };
  return { v: "mode", p: { key, mode: t(`mcp.exposure.mode.${mode}`, { defaultValue: mode }) } };
};
