// frontend/src/pages/sync/syncRemoteForm.ts
//
// The remote form's draft shape and its client-side checks, kept apart from
// the card so they can be tested without rendering it. The daemon validates
// again on PUT (BACKUP_REMOTE_INVALID); these checks exist so the Save button
// can stay disabled until the draft is something the daemon would take.

export interface FormState {
  url: string;
  branch: string;
  credentialRef: string;
  includeCredentials: boolean;
  intervalSeconds: number;
}

/** The spec's defaults, so an unconfigured card opens on them rather than blank. */
export const DEFAULT_BRANCH = "main";
export const DEFAULT_INTERVAL_SECONDS = 3600;
/** A round every minute is the fastest cadence worth supporting. */
export const MIN_INTERVAL_SECONDS = 60;

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

export interface FormErrors {
  url?: "url";
  interval?: "interval";
}

/** Field-keyed error codes — the card maps them to `sync.remote.errors.*`. */
export function validateRemote(form: FormState): FormErrors {
  const errors: FormErrors = {};
  if (!isGitRemoteUrl(form.url)) errors.url = "url";
  if (!Number.isFinite(form.intervalSeconds) || form.intervalSeconds < MIN_INTERVAL_SECONDS)
    errors.interval = "interval";
  return errors;
}

/** Whether the draft differs from what the daemon holds. */
export function isDirty(form: FormState, saved: FormState): boolean {
  return (
    form.url.trim() !== saved.url ||
    form.branch.trim() !== saved.branch ||
    form.credentialRef.trim() !== saved.credentialRef ||
    form.includeCredentials !== saved.includeCredentials ||
    form.intervalSeconds !== saved.intervalSeconds
  );
}
