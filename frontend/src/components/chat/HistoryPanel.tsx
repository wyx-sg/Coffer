// components/chat/HistoryPanel.tsx
// Cross-agent transcript history search (ADR-022): a search box over indexed
// transcripts; clicking a hit browses that session's scrubbed turns read-only.
// Surfaced from the Vault Console history column.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useHistorySearch, useHistoryReindex } from "@/lib/hooks/useHistory";
import type { HistoryHit } from "@/lib/api/history";
import { HistorySessionView } from "./HistorySessionView";

interface Props {
  onClose: () => void;
}

export function HistoryPanel({ onClose }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<HistoryHit | null>(null);
  const { data, isFetching } = useHistorySearch(query);
  const reindex = useHistoryReindex();

  if (selected) {
    return <HistorySessionView hit={selected} onBack={() => setSelected(null)} />;
  }

  const hits = data?.hits ?? [];

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-2 py-2">
        <span className="px-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t("history.title")}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="size-7 p-0"
            onClick={() => reindex.mutate(undefined)}
            disabled={reindex.isPending}
            aria-label={t("history.reindex")}
          >
            <RefreshCw className={reindex.isPending ? "size-4 animate-spin" : "size-4"} />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="size-7 p-0"
            onClick={onClose}
            aria-label={t("history.close")}
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      <div className="border-b border-border p-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("history.searchPlaceholder")}
            aria-label={t("history.searchAria")}
            className="h-8 pl-8 text-sm"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {query.trim() === "" ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">{t("history.prompt")}</p>
        ) : isFetching && hits.length === 0 ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">{t("common.loading")}</p>
        ) : hits.length === 0 ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">{t("history.noResults")}</p>
        ) : (
          <ul className="space-y-1">
            {hits.map((hit) => (
              <li key={`${hit.agent_type}:${hit.session_id}`}>
                <button
                  type="button"
                  onClick={() => setSelected(hit)}
                  className="w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-secondary"
                >
                  <span className="block truncate font-medium">{hit.title}</span>
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                    {hit.agent_type}
                    {hit.project_path ? ` · ${hit.project_path}` : ""}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground/80">
                    {hit.snippet}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
