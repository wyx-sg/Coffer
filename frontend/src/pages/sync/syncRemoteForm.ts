// frontend/src/pages/sync/syncRemoteForm.ts
//
// The remote's draft shape, its client-side checks and its translation to the
// one PUT the daemon takes — kept apart from the forms so they can be tested
// without rendering them. The daemon validates again on PUT.
//
// "Run a round" is one control over two stored fields: a cadence writes
// `interval_seconds` and `enabled: true`; "Only when I press Sync now" writes
// `enabled: false` and keeps the interval, which is how a paused remote reads
// and how it is resumed.
import type { TFunction } from "i18next";

import type { SyncRemote, SyncRemoteInput } from "@/lib/api/sync";

export interface FormState {
  url: string;
  branch: string;
  /** A name in the secret store — never the secret. Empty: none. */
  secretRef: string;
  /** The HTTPS user name the token is sent with. Empty: the daemon's default. */
  username: string;
  includeSecret: boolean;
  intervalSeconds: number;
  /** False: rounds run only when the user presses Sync now. */
  enabled: boolean;
}

/** The spec's defaults, so an unconfigured form opens on them rather than blank. */
const DEFAULT_BRANCH = "main";
const DEFAULT_INTERVAL_SECONDS = 3600;
/** The cadences "Run a round" offers, in seconds. */
export const CADENCES = [900, 3600, 21600, 86400] as const;

export const EMPTY_FORM: FormState = {
  url: "",
  branch: DEFAULT_BRANCH,
  secretRef: "",
  username: "",
  includeSecret: false,
  intervalSeconds: DEFAULT_INTERVAL_SECONDS,
  enabled: true,
};

const URL_SCHEMES = new Set(["http:", "https:", "ssh:", "git:"]);
/** scp-like `git@host:path` — the form git itself accepts without a scheme. */
const SCP_LIKE = /^[\w.-]+@[\w.-]+:[^\s]+$/;

/** A git remote URL: http(s)/ssh/git scheme that parses, or `user@host:path`. */
export function isGitRemoteUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (SCP_LIKE.test(trimmed)) return true;
  try {
    const parsed = new URL(trimmed);
    return URL_SCHEMES.has(parsed.protocol) && parsed.hostname.length > 0;
  } catch {
    return false;
  }
}

/** Only an HTTPS remote sends a user name with its token. */
export function isHttpsUrl(value: string): boolean {
  return /^https:\/\//i.test(value.trim());
}

/** The form a stored remote opens as. The default user name reads as empty. */
export function formFromRemote(remote: SyncRemote | null): FormState {
  if (!remote) return EMPTY_FORM;
  return {
    url: remote.url,
    branch: remote.branch,
    secretRef: remote.secret_ref ?? "",
    username: remote.username === DEFAULT_USERNAME ? "" : remote.username,
    includeSecret: remote.include_secret,
    intervalSeconds: remote.interval_seconds,
    enabled: remote.enabled,
  };
}

/** What the daemon stores when no user name is sent (`SyncRemoteIn.username`). */
const DEFAULT_USERNAME = "coffer";

/**
 * The PUT body. The user name is the form's only for an HTTPS URL; any other
 * remote keeps the one stored (`stored`), since it has no field to change it.
 */
export function toRemoteInput(form: FormState, stored: SyncRemote | null): SyncRemoteInput {
  const username = isHttpsUrl(form.url)
    ? form.username.trim() || DEFAULT_USERNAME
    : (stored?.username ?? DEFAULT_USERNAME);
  return {
    url: form.url.trim(),
    branch: form.branch.trim() || DEFAULT_BRANCH,
    secret_ref: form.secretRef.trim() || null,
    username,
    include_secret: form.includeSecret,
    interval_seconds: form.intervalSeconds,
    enabled: form.enabled,
  };
}

export interface FormErrors {
  url?: "url";
}

/** Field-keyed error codes — the forms map them to `sync.remote.errors.*`. */
export function validateRemote(form: FormState): FormErrors {
  return isGitRemoteUrl(form.url) ? {} : { url: "url" };
}

/** "Every hour", "Every 15 minutes"… — the phrase for one interval. */
export function cadenceLabel(t: TFunction, seconds: number): string {
  if (seconds % 86400 === 0) return t("sync.remote.cadence.days", { count: seconds / 86400 });
  if (seconds % 3600 === 0) return t("sync.remote.cadence.hours", { count: seconds / 3600 });
  return t("sync.remote.cadence.minutes", { count: Math.max(1, Math.round(seconds / 60)) });
}
