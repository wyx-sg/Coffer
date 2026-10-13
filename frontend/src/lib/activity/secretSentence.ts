// frontend/src/lib/activity/secretSentence.ts
//
// The sentences of the secret events: which secret, and for a use where its
// value went. A sentence names a secret by its name, never by its value; no
// audit row carries a value to begin with.
import type { TFunction } from "i18next";

import {
  type Builder,
  type Ctx,
  type Facts,
  type Variant,
  secretPhrase,
  shownPath,
} from "./auditFacts";

/** Variant suffix per destination kind a `SecretDestination` names. */
const DESTINATIONS: Record<string, string> = {
  mcp_server: "mcpServer",
  provider: "provider",
  channel: "channel",
  sync_remote: "syncRemote",
};

/** An environment variable's shape; a header carries a `-` or is `Authorization`. */
const ENV_NAME = /^[A-Z_][A-Z0-9_]*$/;
const HEADER_NAME = /-|^authorization$/i;

/**
 * Where the value went inside its destination, in words. The slot is the key
 * the consumer resolved the secret under: an MCP server's environment variable
 * or header, a custom-tool environment's `<environment>:<header>` (a group from
 * before environments keeps the bare header), a connection's `key`, a channel's
 * `token` / `secret`, the sync remote's `token`.
 */
function slotPhrase(t: TFunction, kind: string, slot: string, customTool: boolean): string {
  const say = (v: string, s = slot) => t(`audit.activity.secret_resolved_slot${v}`, { slot: s });
  if (!slot) return "";
  if (customTool) return say("Header", slot.includes(":") ? slot.split(":").pop() : slot);
  if (kind === "provider" && slot === "key") return say("Key");
  if (kind === "channel" && slot === "token") return say("BotToken");
  if (kind === "channel" && slot === "secret") return say("AppSecret");
  if (kind === "sync_remote" && slot === "token") return say("Token");
  if (kind === "mcp_server" && ENV_NAME.test(slot)) return say("Env");
  if (kind === "mcp_server" && HEADER_NAME.test(slot)) return say("Header");
  return slot;
}

/** Coffer's own hand-off to something it starts or calls: details name the destination. */
function handOff(f: Facts, t: TFunction, secret: string): Variant | null {
  const kind = f.str("destination_kind");
  const name = f.str("destination_name");
  const slot = f.str("slot");
  // A custom-tool group is an MCP server whose slots are `<environment>:<header>`
  // and whose label is `<group> · <environment>`.
  const customTool = kind === "mcp_server" && (slot.includes(":") || name.includes(" · "));
  const dest = customTool ? "customTool" : DESTINATIONS[kind];
  if (!dest) return name ? { v: slot ? "otherSlot" : "other", p: { secret, name, slot } } : null;
  if (dest !== "syncRemote" && !name) return null;
  const where = slotPhrase(t, kind, slot, customTool);
  return { v: where ? `${dest}Slot` : dest, p: { secret, name, slot: where } };
}

/** `coffer run` handed the secret to a program it started: details name the program and folder. */
function cofferRun(f: Facts, secret: string): Variant {
  const argv0 = f.str("argv0");
  const program = argv0.split(/[\\/]/).filter(Boolean).pop() ?? "";
  const cwd = f.str("cwd") ? shownPath(f.str("cwd")) : "";
  if (!program) return { v: "runBare", p: { secret } };
  return { v: cwd ? "run" : "runProgram", p: { secret, program, cwd } };
}

/** A row's secret: the `name` an older row carries, else the one its `ref` names. */
function secretOf(f: Facts, x: Ctx): string {
  const name = f.str("name");
  return name ? x.t("audit.secretNamed", { name }) : secretPhrase(f, x);
}

const secretResolved: Builder = (f, x) => {
  const { t } = x;
  const secret = secretOf(f, x);
  if (!secret) return null;
  if (f.has("destination_kind")) return handOff(f, t, secret) ?? { v: "secret", p: { secret } };
  if (f.has("argv0")) return cofferRun(f, secret);
  return { v: "secret", p: { secret } };
};

/** The approval events: the secret a binding sends, or turning approval off. */
const approval: Builder = (f, x) => {
  const op = f.str("op");
  if (op === "disable_protection") return { v: "disable" };
  const secret = secretPhrase(f, x);
  return op === "bind" && secret ? { v: "bind", p: { secret } } : null;
};

/** An event whose only object is the secret its `ref` names. */
const namedSecret: Builder = (f, x) => {
  const secret = secretPhrase(f, x);
  return secret ? { v: "secret", p: { secret } } : null;
};

const secretSet: Builder = (f, x) => {
  const secret = secretPhrase(f, x);
  if (!secret) return null;
  return { v: f.bool("replaced") ? "replaced" : "secret", p: { secret } };
};

const secretDeleted: Builder = (f, x) => {
  const secret = secretPhrase(f, x);
  if (!secret) return null;
  return {
    v: f.str("reason") === "released_with_resource" ? "released" : "secret",
    p: { secret },
  };
};

/** A plaintext value moved into a secret: where it was found and the secret it became. */
const secretImported: Builder = (f, x) => {
  const secret = secretOf(f, x);
  if (!secret) return null;
  const key = f.str("key");
  const where = f.str("resource") || (f.str("path") ? shownPath(f.str("path")) : "");
  return key && where ? { v: "moved", p: { secret, key, where } } : { v: "secret", p: { secret } };
};

/** The values a person marked, or stopped marking, as not secrets. */
const plaintextPlaces: Builder = (f) => {
  const count = f.list("places")?.length ?? 0;
  return count ? { v: "count", p: { count } } : null;
};

export const SECRET_BUILDERS: Record<string, Builder> = {
  secret_resolved: secretResolved,
  secret_revealed: namedSecret,
  secret_set: secretSet,
  secret_deleted: secretDeleted,
  secret_notes_updated: namedSecret,
  secret_local_access_revoked: namedSecret,
  secret_imported: secretImported,
  secret_approval_requested: approval,
  secret_approval_approved: approval,
  secret_approval_rejected: approval,
  secret_plaintext_ignored: plaintextPlaces,
  secret_plaintext_unignored: plaintextPlaces,
};
