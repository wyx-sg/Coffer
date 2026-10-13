// frontend/src/lib/activity/auditFacts.ts
//
// The typed reads an audit sentence is built from. A row's `details` is a JSON
// object whose shape depends on the event and on the Coffer that wrote it, so
// every read here tolerates a field that is missing or of another type: an old
// row simply reads the sentence without that part.
import type { TFunction } from "i18next";

import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";

export class Facts {
  constructor(readonly raw: Record<string, unknown>) {}

  has(k: string): boolean {
    return k in this.raw;
  }

  /** A non-empty string field, trimmed; "" when absent or not a string. */
  str(k: string): string {
    const v = this.raw[k];
    return typeof v === "string" ? v.trim() : "";
  }

  num(k: string): number | null {
    const v = this.raw[k];
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  }

  bool(k: string): boolean | null {
    const v = this.raw[k];
    return typeof v === "boolean" ? v : null;
  }

  list(k: string): unknown[] | null {
    const v = this.raw[k];
    return Array.isArray(v) ? v : null;
  }

  obj(k: string): Facts | null {
    const v = this.raw[k];
    return v !== null && typeof v === "object" && !Array.isArray(v)
      ? new Facts(v as Record<string, unknown>)
      : null;
  }
}

/** What a builder chose: the variant key's suffix and the values it fills. */
export interface Variant {
  v: string;
  p?: Record<string, unknown>;
}

/** What every builder may read besides `details`. */
export interface Ctx {
  t: TFunction;
  /** The row's `resource_name`, "" when it has none. */
  resource: string;
  /** The secrets as they are named now, by ref; absent until the list loads. */
  secretLabels?: ReadonlyMap<string, string | null>;
}

/**
 * The secret a row's `ref` names, as a phrase of the sentence: by the name a
 * person gave it — today's if the secret still exists, else the one the row
 * recorded (`ref_label`) — and, when nobody named it, as an unnamed secret.
 * The ref itself is a minted id and never reads.
 */
export function secretPhrase(f: Facts, { t, secretLabels }: Ctx, k = "ref"): string {
  const ref = f.str(k);
  if (!ref) return "";
  const name = secretLabels?.get(ref) || f.str("ref_label") || legacyName(ref);
  return name ? t("audit.secretNamed", { name }) : t("audit.secretUnnamed");
}

/** A ref from before ids were minted is its own name; a minted id (32 hex) is not one. */
function legacyName(ref: string): string {
  const last = ref.split("/").filter(Boolean).pop() ?? "";
  return /^[0-9a-f]{32}$/.test(last) ? "" : last;
}

export type Builder = (f: Facts, x: Ctx) => Variant | null;

/**
 * An agent as a reader knows it. Rows name agents by type (`claude_code`) or
 * by their resource name (`claude-code`); either reads as "Claude Code".
 */
export function agentLabel(raw: string): string {
  if (!raw) return "";
  const asType = raw.replace(/-/g, "_");
  const byType = agentTypeLabel(asType);
  return byType !== asType ? byType : raw;
}

/** An absolute path under a home folder reads from `~`; any other path as written. */
export function shownPath(path: string): string {
  return path.startsWith("/") || /^[A-Za-z]:[\\/]/.test(path) ? abbreviateHomePath(path) : path;
}

/** A commit id at the length people quote it. */
export function shortCommit(commit: string): string {
  return /^[0-9a-f]{12,}$/i.test(commit) ? commit.slice(0, 7) : commit;
}

/** A list of names in the reader's language ("a, b" / "a、b"). */
export function joinNames(t: TFunction, names: readonly string[]): string {
  return names.join(t("audit.activity.resource_scope_updated_separator"));
}

/** The length of an array field, or a number field itself. */
export function countOf(f: Facts, k: string): number {
  const asList = f.list(k);
  return asList ? asList.length : (f.num(k) ?? 0);
}
