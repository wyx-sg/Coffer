// frontend/src/kinds/memory/MemoryRecallPanel.tsx
//
// Recall section: a keyword/vector mode toggle, the query box, and the ranked
// hits. State and the recall trigger live in the page.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import { type RecallResponse, type RetrievalMode } from "./api";

interface Props {
  query: string;
  mode: RetrievalMode;
  result: RecallResponse | null;
  error: unknown;
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onModeChange: (mode: RetrievalMode) => void;
  onRecall: () => void;
}

export function MemoryRecallPanel({
  query,
  mode,
  result,
  error,
  isPending,
  onQueryChange,
  onModeChange,
  onRecall,
}: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{t("memory.detail.recall")}</h2>
      <div className="flex max-w-2xl flex-wrap gap-2">
        <select
          aria-label={t("memory.detail.mode")}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={mode}
          onChange={(e) => onModeChange(e.target.value as RetrievalMode)}
        >
          <option value="keyword">{t("memory.modes.keyword")}</option>
          <option value="vector">{t("memory.modes.vector")}</option>
        </select>
        <Input
          className="flex-1"
          placeholder={t("memory.detail.recallPlaceholder")}
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim()) onRecall();
          }}
        />
        <Button onClick={onRecall} disabled={!query.trim() || isPending}>
          {t("memory.detail.recall")}
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{translateApiError(t, error)}</p> : null}
      {result ? (
        <div className="space-y-2">
          {result.fallback ? (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t("memory.detail.fallback")}
            </p>
          ) : null}
          {result.hits.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {result.hits.map((h, i) => (
                <li key={h.id} className="rounded border p-2">
                  <div className="font-medium">
                    {i + 1}.{" "}
                    <span className="text-xs text-muted-foreground">
                      {t("memory.detail.score", { score: h.score.toFixed(3) })} · {h.source}
                    </span>
                  </div>
                  <div className="break-words">{h.text}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("memory.detail.noMatches")}</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
