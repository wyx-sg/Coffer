// src/lib/clis/format.ts — pure helpers the CLIs surfaces share: status tone, the list's groups, "checked … ago".
//
// No React and no i18n instance: callers pass `t` or a locale in, so the rules
// are the same on the CLIs page and a skill's Requires tab.
import type { StatusTone } from "@/lib/statusTone";
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
): { needsAttention: Cli[]; ready: Cli[] } {
  const q = filter.trim().toLowerCase();
  const shown = q
    ? items.filter((c) => `${c.command} ${c.title ?? ""}`.toLowerCase().includes(q))
    : items;
  return {
    needsAttention: shown.filter((c) => c.status !== "ready"),
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

/** A skill's name followed by the profiles that declare the requirement:
 *  "coffer-investigating-logs · shopee-account"; the bare name for SKILL.md. */
export function withProfiles(name: string, profiles: readonly string[] | undefined): string {
  return [name, ...(profiles ?? [])].join(" · ");
}

/** The MCP servers started with the command, by name, comma-joined. */
export function serverNames(cli: Pick<Cli, "needed_by_servers">): string {
  return cli.needed_by_servers.map((s) => s.server_name).join(", ");
}

type T = (key: string, options?: Record<string, unknown>) => string;

/** How the two places word who needs a command: the list row ("1 MCP server,
 *  1 skill") and the sentences ("1 MCP server and 1 skill"). */
const NEEDED_STYLE = {
  list: { pair: "clis.listPair", coffer: "clis.withCofferList" },
  sentence: { pair: "clis.neededPair", coffer: "clis.withCofferSentence" },
} as const;

/** How many need the command: Coffer itself counts as one. */
export function neededTotal(
  cli: Pick<Cli, "needed_by" | "needed_by_servers" | "needed_by_coffer">,
): number {
  return (
    cli.needed_by.length + cli.needed_by_servers.length + (cli.needed_by_coffer.length > 0 ? 1 : 0)
  );
}

/** Who needs the command, counted: "2 skills", "1 MCP server and 1 skill",
 *  "Coffer and 1 skill". */
export function neededByCount(
  t: T,
  cli: Pick<Cli, "needed_by" | "needed_by_servers" | "needed_by_coffer">,
  style: keyof typeof NEEDED_STYLE = "sentence",
): string {
  const skills = cli.needed_by.length;
  const servers = cli.needed_by_servers.length;
  const skillPart = t("clis.skillCount", { count: skills });
  const serverPart = t("clis.mcpServerCount", { count: servers });
  const rest =
    servers === 0
      ? skills === 0
        ? null
        : skillPart
      : skills === 0
        ? serverPart
        : t(NEEDED_STYLE[style].pair, { servers: serverPart, skills: skillPart });
  if (cli.needed_by_coffer.length === 0) return rest ?? skillPart;
  return rest === null ? "Coffer" : t(NEEDED_STYLE[style].coffer, { rest });
}

/** "today at 14:32", or "3 Oct at 14:32" for an older probe, in the reader's language. */
export function checkedWhen(t: T, iso: string, locale: string, now: number = Date.now()): string {
  const at = new Date(iso);
  const time = at.toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  if (at.toDateString() === new Date(now).toDateString()) return t("clis.detail.today", { time });
  const date = at.toLocaleDateString(locale, { day: "numeric", month: "short" });
  return t("clis.detail.onDate", { date, time });
}
