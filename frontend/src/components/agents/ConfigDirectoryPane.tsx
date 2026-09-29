// frontend/src/components/agents/ConfigDirectoryPane.tsx — spec agent-registry.
// Right pane of the Config files tab when a directory entry (Claude Code's
// agents/) is selected: its name, how many files it holds and what it is for,
// and those files as a list — picking one opens it, as the tree does.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { FileActions } from "@/components/FileActions";
import { FILE_PANE_BODY, FILE_PANE_SCROLL } from "@/components/filePane";
import { baseName } from "@/lib/agents/configFiles";
import type { ConfigFileInfo } from "@/lib/api/agents";
import { cn, formatBytes, formatDateTime } from "@/lib/utils";

export function ConfigDirectoryPane({
  entry,
  description,
  onSelectChild,
}: {
  entry: ConfigFileInfo;
  description?: string | null;
  onSelectChild: (relpath: string) => void;
}) {
  const { t } = useTranslation();
  const children = entry.files ?? [];
  return (
    <div className={FILE_PANE_BODY}>
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="break-all font-mono text-sm font-medium text-text">
              {`${baseName(entry.path)}/`}
            </span>
            <span className="text-2xs text-text-subtle">
              {t("agents.configTab.directoryCount", { count: children.length })}
            </span>
          </p>
          {description ? <p className="mt-0.5 text-xs text-text-muted">{description}</p> : null}
        </div>
        {entry.exists ? <FileActions filePath={entry.path} /> : null}
      </div>

      {children.length === 0 ? (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-text-muted">
          {t("agents.config.emptyDir")}
        </div>
      ) : (
        <ul className={cn("divide-y divide-border-subtle rounded-md border", FILE_PANE_SCROLL)}>
          {children.map((c) => (
            <li key={c.relpath}>
              <button
                type="button"
                onClick={() => onSelectChild(c.relpath)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-hover"
              >
                <FileText className="size-3.5 shrink-0 text-text-muted" aria-hidden />
                <span className="min-w-0 flex-1 break-all font-mono text-xs text-text">
                  {c.relpath}
                </span>
                <span className="shrink-0 text-2xs text-text-subtle">
                  {`${formatBytes(c.size)} · ${formatDateTime(c.modified_at).slice(0, 10)}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="shrink-0 space-y-0.5 text-2xs text-text-subtle">
        <p>{t("agents.configTab.directoryHint")}</p>
        <p className="break-all font-mono">{entry.path}</p>
      </div>
    </div>
  );
}
