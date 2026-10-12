// frontend/src/lib/activity/auditSentence.ts
//
// Which sentence an audit row reads as, and what fills it. Each event has a
// plain sentence at `audit.activity.<event>` — what a row with none of the
// fields below says, and what the Activity search matches — and may have
// variants at `audit.activity.<event>_<variant>` that name what the row acted
// on. A builder picks the variant the row's `details` can fill completely, so
// a missing field drops the part it would have filled rather than leaving a
// hole in the sentence.
import type { TFunction } from "i18next";

import {
  type Builder,
  type Ctx,
  Facts,
  type Variant,
  agentLabel,
  countOf,
  joinNames,
  shownPath,
} from "./auditFacts";
import { SECRET_BUILDERS } from "./secretSentence";
import {
  memorySynced,
  memorySyncUndone,
  projectionRefused,
  projectionRepaired,
  providerSwitched,
  resourceRenamed,
  scopeUpdated,
  retentionUpdated,
  onOff,
  skillUpdated,
  skillUnmanagedDeleted,
  syncRun,
  toolExposure,
} from "./auditBuilders";

/** One string field, named in the sentence as `param`. */
function field(key: string, variant: string, param = key): Builder {
  return (f) => (f.str(key) ? { v: variant, p: { [param]: f.str(key) } } : null);
}

/** A path field, shown from `~` when it is absolute. */
function pathField(key: string, variant = "path"): Builder {
  return (f) => (f.str(key) ? { v: variant, p: { path: shownPath(f.str(key)) } } : null);
}

/** A details field that is an agent, read by its product name. */
function agentField(key: string, variant = "agent"): Builder {
  return (f) => (f.str(key) ? { v: variant, p: { agent: agentLabel(f.str(key)) } } : null);
}

/** Needs the row's resource too: without it the plain sentence is the honest one. */
function withResource(b: Builder): Builder {
  return (f, x) => (x.resource ? b(f, x) : null);
}

const capability: Builder = (f, { t }) => {
  const key = f.str("capability_key") || f.str("key");
  if (!key) return null;
  const raw = f.str("capability_type");
  return raw
    ? { v: "key", p: { key, capType: t(`audit.capType.${raw}`, { defaultValue: raw }) } }
    : { v: "keyOnly", p: { key } };
};

const engineSetting: Builder = (f) => {
  if (f.has("transcribe_model") || f.has("transcribe_model_from")) {
    const to = f.str("transcribe_model");
    const from = f.str("transcribe_model_from");
    if (to)
      return from && from !== to
        ? { v: "transcribeChange", p: { from, to } }
        : { v: "transcribe", p: { to } };
    return from ? { v: "transcribeCleared", p: { from } } : null;
  }
  if (f.str("pass") !== "memory_sync") return null;
  const on = f.bool("enabled_to");
  if (on !== null && on !== f.bool("enabled_from")) return { v: on ? "syncOn" : "syncOff" };
  const from = f.num("interval_s_from");
  const to = f.num("interval_s_to");
  if (from !== null && to !== null && from !== to) {
    return { v: "syncInterval", p: { from: Math.round(from / 60), to: Math.round(to / 60) } };
  }
  return null;
};

const knowledgeEdited: Builder = (f) => {
  if (f.bool("collection_restored")) return { v: "collectionRestored" };
  if (f.has("restored_from")) {
    const count = countOf(f, "paths") || (f.num("count") ?? 0);
    return count ? { v: "restored", p: { count } } : null;
  }
  if (f.bool("description")) return { v: "description" };
  return f.str("path") ? { v: "path", p: { path: f.str("path") } } : null;
};

const knowledgeWritten: Builder = (f) => {
  if (f.str("title")) return { v: "title", p: { title: f.str("title") } };
  return f.str("path") ? { v: "path", p: { path: f.str("path") } } : null;
};

const keyLocation = (t: TFunction, raw: string) =>
  t(`audit.activity.master_key_relocated_at_${raw}`, { defaultValue: raw });

const masterKeyRelocated: Builder = (f, { t }) => {
  const from = f.str("from");
  const to = f.str("to");
  if (!to) return null;
  return from
    ? { v: "change", p: { from: keyLocation(t, from), to: keyLocation(t, to) } }
    : { v: "to", p: { to: keyLocation(t, to) } };
};

const masterKeyImported: Builder = (f) => {
  const fingerprint = f.str("fingerprint");
  if (!fingerprint) return null;
  const replaced = f.str("replaced");
  return replaced
    ? { v: "replaced", p: { fingerprint, replaced } }
    : { v: "key", p: { fingerprint } };
};

const BUILDERS: Record<string, Builder> = {
  ...SECRET_BUILDERS,
  agent_config_file_deleted: field("key", "key"),
  agent_config_file_written: field("key", "key"),
  agent_mcp_entry_adopted: field("entry", "entry"),
  agent_mcp_entry_removed: field("entry", "entry"),
  agent_mcp_installed: (f, x) =>
    f.list("repaired")?.length ? { v: "repaired" } : pathField("path")(f, x),
  agent_mcp_uninstalled: pathField("path"),
  agent_plugin_toggled: (f) => {
    const plugin = f.str("plugin");
    const on = f.bool("enabled");
    return plugin && on !== null ? { v: on ? "on" : "off", p: { plugin } } : null;
  },
  agent_plugin_uninstalled: field("plugin", "plugin"),
  capability_enabled: capability,
  capability_disabled: capability,
  channel_paired: withResource((f) => {
    const person = f.str("display_name");
    return person ? { v: "person", p: { person } } : null;
  }),
  channel_person_removed: withResource((f) => {
    const person = f.str("display_name") || f.str("sender_id");
    return person ? { v: "person", p: { person } } : null;
  }),
  channel_reply_withdrawn: withResource((f) => {
    const count = f.num("messages");
    return count ? { v: "count", p: { count } } : null;
  }),
  internal_engine_model_set: engineSetting,
  knowledge_deleted: withResource(field("path", "path")),
  knowledge_edited: withResource(knowledgeEdited),
  knowledge_written: withResource(knowledgeWritten),
  master_key_exported: pathField("path"),
  master_key_imported: masterKeyImported,
  master_key_relocated: masterKeyRelocated,
  memory_hook_removed: (_f, { resource }) =>
    resource ? { v: "agent", p: { agent: agentLabel(resource) } } : null,
  memory_synced: memorySynced,
  memory_sync_undone: memorySyncUndone,
  memory_curation_requested: agentField("agent_type"),
  provider_transcribe_default_set: withResource((f, { resource }) => {
    const from = f.str("from");
    return from && from !== resource ? { v: "from", p: { from } } : null;
  }),
  provider_projection_refused: projectionRefused,
  provider_projection_repaired: projectionRepaired,
  provider_switched: providerSwitched,
  resource_renamed: resourceRenamed,
  resource_scope_updated: scopeUpdated,
  retention_updated: retentionUpdated,
  call_content_recording_updated: onOff("to"),
  daemon_residency_updated: onOff("login_service_installed"),
  daemon_restarted: (f) => (f.num("port") ? { v: "port", p: { port: f.num("port") } } : null),
  skill_adopted: withResource(agentField("agent")),
  skill_relinked: withResource(agentField("agent")),
  skill_drift_remediated: withResource(agentField("agent")),
  skill_unmanaged_deleted: skillUnmanagedDeleted,
  skill_updated: withResource(skillUpdated),
  skill_update_merged: withResource(skillUpdated),
  sync_run: syncRun,
  sync_rolled_back: (f) =>
    f.num("round") !== null ? { v: "round", p: { round: f.num("round") } } : null,
  sync_machine_removed: (f) => {
    const name = f.str("name") || f.str("hostname");
    return name ? { v: "name", p: { name } } : null;
  },
  sync_plaintext_pushed: (f, { t }) => {
    const files = (f.list("files") ?? []).filter((x): x is string => typeof x === "string");
    return files.length ? { v: "files", p: { files: joinNames(t, files) } } : null;
  },
  tool_exposure_changed: toolExposure,
  cli_tool_added: field("command", "command"),
  cli_tool_edited: field("command", "command"),
  cli_tool_removed: field("command", "command"),
  vault_file_edited: field("path", "path"),
  vault_file_restored: field("path", "path"),
  attention_ignored: field("title", "title"),
};

/** The variant of `eventType` this row's details fill, if any. */
export function auditVariant(
  eventType: string,
  details: Record<string, unknown>,
  ctx: Ctx,
): Variant | null {
  const build = BUILDERS[eventType];
  return build ? build(new Facts(details), ctx) : null;
}
