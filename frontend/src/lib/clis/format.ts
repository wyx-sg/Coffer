// src/lib/clis/format.ts — pure helpers the CLIs surfaces share: status tone, the list's groups, "checked … ago".
//
// No React and no i18n instance: callers pass `t` or a locale in, so the rules
// are the same on the CLIs page and a skill's Requires tab.
import type { StatusTone } from "@/components/status/statusTone";
import type { Cli, CliStatus } from "@/lib/api/clis";

const TONE: Record<CliStatus, StatusTone> = {
  missing: "err",
  outdated: "warn",
  logged_out: "warn",
  ready: "ok",
};

export function cliTone(status: CliStatus): StatusTone {
  return TONE[status];
}

/** The list pane's two groups, each in the daemon's order (problems first:
 *  missing, too old, not logged in), narrowed to commands matching `filter`. */
export function groupClis(
  items: readonly Cli[],
  filter: string,
): { needsYou: Cli[]; ready: Cli[] } {
  const q = filter.trim().toLowerCase();
  const shown = q
    ? items.filter((c) => `${c.command} ${c.title ?? ""}`.toLowerCase().includes(q))
    : items;
  return {
    needsYou: shown.filter((c) => c.status !== "ready"),
    ready: shown.filter((c) => c.status === "ready"),
  };
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

/** The skills that need the command, by name, comma-joined. */
export function skillNames(cli: Pick<Cli, "needed_by">): string {
  return cli.needed_by.map((n) => n.skill_name).join(", ");
}
