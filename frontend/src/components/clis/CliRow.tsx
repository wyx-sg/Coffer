// src/components/clis/CliRow.tsx — one command in the CLIs list pane (board CliList): a status dot, its name, one status line.
//
// The status line says what is wrong, in the problem's colour ("Not found · 2
// skills need it", "Not found · duckdb can't start" for a launcher an MCP
// server starts with, "24.0.2 · needs ≥ 25.0", "Not logged in · 3 skills need
// it") or, when ready, in grey: the version, "logged in" where a login is
// declared, and who needs it — or "added by you" for a tool nothing needs.
import { useTranslation } from "react-i18next";

import type { Cli } from "@/lib/api/clis";
import { neededByCount, neededTotal, serverNames } from "@/lib/clis/format";
import { cn } from "@/lib/utils";

interface Props {
  cli: Cli;
  selected: boolean;
  onOpen: () => void;
}

function useStatusLine(cli: Cli): string {
  const { t } = useTranslation();
  const version = cli.version ?? t("clis.unknownVersion");
  const count = neededTotal(cli);
  const who = neededByCount(t, cli, "list");
  const needIt = (lead: string) => t("clis.list.needLine", { lead, who, count });
  switch (cli.status) {
    case "missing":
      return cli.needed_by_servers.length > 0
        ? t("clis.list.missingServersLine", {
            servers: serverNames(cli),
            count: cli.needed_by_servers.length,
          })
        : needIt(t("clis.status.missing"));
    case "outdated":
      return t("clis.list.outdatedLine", { version, min: cli.min_version ?? "" });
    case "logged_out":
      return needIt(t("clis.status.logged_out"));
    case "ready":
      return [
        version,
        cli.login.state === "logged_in" ? t("clis.list.loggedIn") : null,
        count > 0 ? who : t("clis.list.addedByYou"),
      ]
        .filter(Boolean)
        .join(" · ");
  }
}

const TONE = {
  missing: "text-danger",
  outdated: "text-warning",
  logged_out: "text-warning",
  ready: "text-success",
} as const;

export function CliRow({ cli, selected, onOpen }: Props) {
  const line = useStatusLine(cli);
  return (
    <li>
      <button
        type="button"
        aria-current={selected ? "page" : undefined}
        onClick={onOpen}
        className={cn(
          "flex min-h-[52px] w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors duration-fast",
          selected ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <span
          aria-hidden
          className={cn("size-1.5 shrink-0 rounded-full bg-current", TONE[cli.status])}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-sm font-label text-text">
            {cli.command}
          </span>
          <span
            className={cn(
              "block truncate text-xs",
              cli.status === "ready" ? "text-text-muted" : TONE[cli.status],
            )}
          >
            {line}
          </span>
        </span>
      </button>
    </li>
  );
}
