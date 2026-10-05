// src/components/clis/ClisList.tsx — the CLIs list pane: a filter ("/" focuses it) with Check beside it, then Needs attention and Ready.
//
// Needs attention holds the commands that are missing, too old or not logged in, in
// the daemon's order; Ready the rest. A row opens
// `/clis/<command>` in the detail pane beside it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { ListLoadError, ListLoadingRows, ListNoMatch } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
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
  /** Check: re-probe every command. */
  onCheck: () => void;
  checking: boolean;
}

export function ClisList({
  items,
  loading,
  error,
  onRetry,
  selected,
  onOpen,
  onCheck,
  checking,
}: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const { needsAttention, ready } = groupClis(items, filter);
  const groups = [
    { key: "needsAttention", rows: needsAttention },
    { key: "ready", rows: ready },
  ].filter((g) => g.rows.length > 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <div className="flex items-center gap-1">
        <SearchInput
          className="min-w-0 flex-1"
          value={filter}
          onChange={setFilter}
          placeholder={t("clis.search")}
          ariaLabel={t("clis.search")}
          shortcut="/"
        />
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0"
          title={t("clis.checkHint")}
          onClick={onCheck}
          disabled={checking}
        >
          <RefreshCw aria-hidden className={checking ? "animate-spin" : undefined} />
          {checking ? t("clis.checking") : t("clis.check")}
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {error ? (
          <ListLoadError kind="clis" error={error} onRetry={() => onRetry?.()} />
        ) : loading ? (
          <ListLoadingRows />
        ) : groups.length === 0 ? (
          <ListNoMatch kind="clis" query={filter} onClear={() => setFilter("")} />
        ) : (
          groups.map(({ key, rows }) => (
            <section key={key} className="mb-3" aria-label={t(`clis.list.${key}`)}>
              <h2
                aria-hidden
                className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted"
              >
                {t(`clis.list.${key}`)}
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
