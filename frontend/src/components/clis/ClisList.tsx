// src/components/clis/ClisList.tsx — the CLIs list pane: a filter ("/" focuses it), then Needs attention and Ready.
//
// Needs attention holds the commands that are missing, too old or not logged in, in
// the daemon's order; Ready the rest. Each group carries its count. A row opens
// `/clis/<command>` in the detail pane beside it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import type { Cli } from "@/lib/api/clis";
import { groupClis } from "@/lib/clis/format";
import { CliRow } from "./CliRow";

interface Props {
  items: Cli[];
  loading: boolean;
  /** The list read failed: the pane shows the error block under the filter. */
  error?: unknown;
  onRetry?: () => void;
  selected: string | null;
  onOpen: (command: string) => void;
}

export function ClisList({ items, loading, error, onRetry, selected, onOpen }: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const { needsAttention, ready } = groupClis(items, filter);
  const groups = [
    { key: "needsAttention", rows: needsAttention },
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
        {error ? (
          <ListLoadError kind="clis" error={error} onRetry={() => onRetry?.()} />
        ) : loading ? (
          <ListLoadingRows />
        ) : groups.length === 0 ? (
          <ListNoMatch kind="clis" query={filter} onClear={() => setFilter("")} />
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
