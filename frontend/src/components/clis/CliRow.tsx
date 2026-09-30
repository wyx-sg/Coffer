// src/components/clis/CliRow.tsx — one command in the CLIs list pane: its name, one status line, how many MCP servers and skills need it.
//
// The status line says what is wrong ("Not found", "Not found · duckdb needs
// it" for a launcher an MCP server starts with, "24.0.2 · needs ≥ 25.0",
// "Not logged in") or, when ready, the version found and — where a login is
// declared — that it is logged in.
import { useTranslation } from "react-i18next";

import type { Cli } from "@/lib/api/clis";
import { neededByCount, serverNames } from "@/lib/clis/format";
import { cn } from "@/lib/utils";

interface Props {
  cli: Cli;
  selected: boolean;
  onOpen: () => void;
}

function useStatusLine(cli: Cli): string {
  const { t } = useTranslation();
  const version = cli.version ?? t("clis.unknownVersion");
  switch (cli.status) {
    case "missing":
      return cli.needed_by_servers.length > 0
        ? t("clis.list.missingServersLine", {
            servers: serverNames(cli),
            count: cli.needed_by_servers.length,
          })
        : t("clis.status.missing");
    case "outdated":
      return t("clis.list.outdatedLine", { version, min: cli.min_version ?? "" });
    case "logged_out":
      return t("clis.status.logged_out");
    case "ready":
      return cli.login.state === "logged_in" ? t("clis.list.loggedInLine", { version }) : version;
  }
}

export function CliRow({ cli, selected, onOpen }: Props) {
  const { t } = useTranslation();
  const line = useStatusLine(cli);
  return (
    <li>
      <button
        type="button"
        aria-current={selected ? "page" : undefined}
        onClick={onOpen}
        className={cn(
          "flex min-h-[52px] w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors duration-fast",
          selected ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-sm font-label text-text">
            {cli.command}
          </span>
          <span
            className={cn(
              "block truncate text-xs",
              cli.status === "missing"
                ? "text-danger"
                : cli.status === "ready"
                  ? "text-text-muted"
                  : "text-warning",
            )}
          >
            {line}
          </span>
        </span>
        <span className="shrink-0 text-xs text-text-muted">{neededByCount(t, cli, "row")}</span>
      </button>
    </li>
  );
}
