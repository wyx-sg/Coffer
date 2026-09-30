// src/components/clis/ClisList.tsx — the CLIs list pane: a filter ("/" focuses it), then Needs you and Ready.
//
// Needs you holds the commands that are missing, too old or not logged in, in
// the daemon's order; Ready the rest. Each group carries its count. A row opens
// `/clis/<command>` in the detail pane beside it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Skeleton } from "@/components/ui/skeleton";
import type { Cli } from "@/lib/api/clis";
import { groupClis } from "@/lib/clis/format";
import { CliRow } from "./CliRow";

interface Props {
  items: Cli[];
  loading: boolean;
  selected: string | null;
  onOpen: (command: string) => void;
}

export function ClisList({ items, loading, selected, onOpen }: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const { needsYou, ready } = groupClis(items, filter);
  const groups = [
    { key: "needsYou", rows: needsYou },
    { key: "ready", rows: ready },
  ].filter((g) => g.rows.length > 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <SearchInput
        value={filter}
        onChange={setFilter}
        placeholder={t("clis.search")}
        ariaLabel={t("clis.search")}
        shortcut="/"
      />
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : groups.length === 0 ? (
          <p className="px-2 text-xs text-text-muted">{t("clis.list.noMatch")}</p>
        ) : (
          groups.map(({ key, rows }) => (
            <section key={key} aria-label={t(`clis.list.${key}`)}>
              <h2
                aria-hidden
                className="mb-1 flex items-center justify-between px-2 text-2xs font-semibold uppercase tracking-wider text-text-subtle"
              >
                {t(`clis.list.${key}`)}
                <span className="font-normal">{rows.length}</span>
              </h2>
              <ul>
                {rows.map((cli) => (
                  <CliRow
                    key={cli.command}
                    cli={cli}
                    selected={cli.command === selected}
                    onOpen={() => onOpen(cli.command)}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </div>
  );
}
