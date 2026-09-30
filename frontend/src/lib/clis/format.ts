// src/lib/clis/format.ts — pure helpers the CLIs pages share: status tone, the summary counts, "checked … ago".
//
// No React and no i18n instance: callers pass `t` or a locale in, so the rules
// are the same on the list, the detail page and a skill's Requires tab.
import type { StatusTone } from "@/components/status/statusTone";
import type { Cli, CliStatus } from "@/lib/api/clis";

/** Problems first — the order the daemon lists rows in, and the summary's. */
export const CLI_STATUSES: readonly CliStatus[] = ["missing", "outdated", "logged_out", "ready"];

const TONE: Record<CliStatus, StatusTone> = {
  missing: "err",
  outdated: "warn",
  logged_out: "warn",
  ready: "ok",
};

export function cliTone(status: CliStatus): StatusTone {
  return TONE[status];
}

/** How many rows are in each status. */
export function countByStatus(items: readonly Cli[]): Record<CliStatus, number> {
  const counts: Record<CliStatus, number> = { missing: 0, outdated: 0, logged_out: 0, ready: 0 };
  for (const item of items) counts[item.status] += 1;
  return counts;
}

/** The oldest probe among `items` — what "Checked … ago" honestly reports. */
export function oldestCheck(items: readonly Pick<Cli, "checked_at">[]): string | null {
  let oldest: string | null = null;
  for (const { checked_at } of items) {
    if (oldest === null || Date.parse(checked_at) < Date.parse(oldest)) oldest = checked_at;
  }
  return oldest;
}

const UNITS: readonly [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "2 minutes ago", "just now"-ish ("now") in the reader's language. */
export function relativeTime(iso: string, locale: string, now: number = Date.now()): string {
  const seconds = Math.round((Date.parse(iso) - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "short" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(0, "second");
}

/** Whether Coffer can run the Homebrew command for this row: something to
 *  install or upgrade, and a declared formula to do it with. */
export function isInstallable(cli: Cli): boolean {
  return (
    (cli.status === "missing" || cli.status === "outdated") &&
    cli.brew !== null &&
    cli.install_command !== null
  );
}

/** The skills that need the command, by name, comma-joined. */
export function skillNames(cli: Pick<Cli, "needed_by">): string {
  return cli.needed_by.map((n) => n.skill_name).join(", ");
}
