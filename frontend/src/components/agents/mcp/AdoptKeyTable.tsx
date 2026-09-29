// src/components/agents/mcp/AdoptKeyTable.tsx — the adopt dialog's Key · Value in Coffer · Store as grid.
//
// Board 2.1.24. A secret-looking key moves into Coffer's encrypted vault, and
// its row edits the credential reference the adopted config will carry; the
// value itself never passes through this form (the daemon moves it). Any other
// key keeps its value as it is, which the daemon never sends to the UI.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";

interface Props {
  title: string;
  keys: readonly string[];
  secret: ReadonlySet<string>;
  refs: Record<string, string>;
  onRefChange: (key: string, ref: string) => void;
}

const GRID = "grid grid-cols-[120px_minmax(0,1fr)_110px] items-center gap-3";

export function AdoptKeyTable({ title, keys, secret, refs, onRefChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-label text-text">{title}</p>
      <div className="rounded-md border border-border-subtle">
        <div
          className={`${GRID} border-b border-border-subtle px-3 py-1.5 text-2xs text-text-muted`}
        >
          <span>{t("agents.mcpTab.adoptDialog.key")}</span>
          <span>{t("agents.mcpTab.adoptDialog.value")}</span>
          <span>{t("agents.mcpTab.adoptDialog.storeAs")}</span>
        </div>
        {keys.map((key) => (
          <div key={key} className={`${GRID} px-3 py-1.5`}>
            <span className="break-all font-mono text-xs text-text">{key}</span>
            {secret.has(key) ? (
              <Input
                aria-label={`${t("agents.mcpTab.adoptDialog.value")}: ${key}`}
                value={refs[key] ?? ""}
                onChange={(e) => onRefChange(key, e.target.value)}
                className="h-7 font-mono text-xs"
              />
            ) : (
              <span className="text-xs text-text-muted">
                {t("agents.mcpTab.adoptDialog.unchanged")}
              </span>
            )}
            <span className="text-xs text-text-muted">
              {secret.has(key)
                ? t("agents.mcpTab.adoptDialog.secret")
                : t("agents.mcpTab.adoptDialog.plain")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
