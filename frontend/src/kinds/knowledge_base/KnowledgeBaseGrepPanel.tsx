// frontend/src/kinds/knowledge_base/KnowledgeBaseGrepPanel.tsx
//
// Grep section: a literal pattern box over the raw Markdown files plus the
// rendered hits. State and the grep trigger live in the page.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import { type GrepResponse } from "./api";

interface Props {
  pattern: string;
  result: GrepResponse | null;
  error: unknown;
  isPending: boolean;
  onPatternChange: (value: string) => void;
  onGrep: () => void;
}

export function KnowledgeBaseGrepPanel({
  pattern,
  result,
  error,
  isPending,
  onPatternChange,
  onGrep,
}: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{t("knowledgeBases.detail.grep")}</h2>
      <div className="flex gap-2">
        <Input
          placeholder={t("knowledgeBases.detail.grepPlaceholder")}
          value={pattern}
          onChange={(e) => onPatternChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && pattern.trim()) onGrep();
          }}
        />
        <Button onClick={onGrep} disabled={!pattern.trim() || isPending}>
          {t("knowledgeBases.detail.grep")}
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{translateApiError(t, error)}</p> : null}
      {result ? (
        result.hits.length > 0 ? (
          <ul className="space-y-1 font-mono text-xs">
            {result.hits.map((h, i) => (
              <li key={`${h.path}:${h.line_number}:${i}`} className="rounded border p-2">
                <span className="text-muted-foreground">
                  {h.path}:{h.line_number}
                </span>{" "}
                {h.line}
              </li>
            ))}
            {result.truncated ? (
              <li className="text-muted-foreground">{t("knowledgeBases.detail.truncated")}</li>
            ) : null}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("knowledgeBases.detail.noMatches")}</p>
        )
      ) : null}
    </section>
  );
}
