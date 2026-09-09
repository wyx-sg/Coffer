// frontend/src/kinds/mcp/ToolTieringNotice.tsx
//
// ADR-046 makes tools/list policy-dependent, which turns "why can't the agent
// see tool X" into a question the UI has to be able to answer. This is that
// answer. It renders nothing when nothing is hidden — a notice that is always
// on stops being read.
import { useTranslation } from "react-i18next";
import { Layers } from "lucide-react";
import { useToolTiering } from "@/lib/hooks/useToolTiering";

export function ToolTieringNotice() {
  const { t } = useTranslation();
  const { data } = useToolTiering();

  if (!data || !data.enabled || data.hidden <= 0) return null;

  return (
    <div
      className="flex items-start gap-2 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
      data-testid="tool-tiering-notice"
    >
      <Layers className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p>
        {t("mcp.tiering.summary", {
          listed: data.listed,
          total: data.total,
          hidden: data.hidden,
        })}{" "}
        <span className="opacity-80">{t("mcp.tiering.hint")}</span>
      </p>
    </div>
  );
}
