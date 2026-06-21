// frontend/src/kinds/memory/MemoryRecallPanel.tsx
//
// Recall section: ONE query box + Recall button, and the ranked hits. External
// retrieval is "one query → one answer" — the backend auto-selects the strategy
// and returns ranked hits (no mode picker, no fallback hint). State and the
// recall trigger live in the page.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import { type RecallResponse } from "./api";

interface Props {
  query: string;
  result: RecallResponse | null;
  error: unknown;
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onRecall: () => void;
}

export function MemoryRecallPanel({
  query,
  result,
  error,
  isPending,
  onQueryChange,
  onRecall,
}: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{t("memory.detail.recall")}</h2>
      <div className="flex max-w-2xl flex-wrap gap-2">
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
