// frontend/src/components/agents/ConfigDirectoryPane.tsx — spec agent-registry.
// Right pane of the Config files tab when a directory entry (Claude Code's
// agents/) is selected (boards 2.1.46–2.1.48): the toolbar with the folder's
// path and New file, one row per file — name, what it is (its own front
// matter's description), size · date, a ⋯ menu (Open file · Reveal in Finder ·
// Delete…) — and a status line saying what the folder is for. Picking a row
// opens the file, as the tree does.
import { useTranslation } from "react-i18next";
import { FilePlus, FileText } from "lucide-react";

import { ViewerToolbar } from "@/components/files/ViewerToolbar";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { ConfigFileInfo } from "@/lib/api/agents";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useAgentConfigChild } from "@/lib/hooks/useAgents";
import { splitFrontmatter } from "@/lib/preview/frontmatter";
import { shortDay } from "@/lib/skills/format";
import { formatBytes } from "@/lib/utils";

type Child = NonNullable<ConfigFileInfo["files"]>[number];

/** The `description:` of a file's front matter, once its content has loaded. */
function useChildDescription(agentUid: string, key: string, relpath: string): string | null {
  const content = useAgentConfigChild(agentUid, key, relpath).data?.content;
  if (!content) return null;
  const hit = splitFrontmatter(content).entries.find((e) => e.key === "description");
  const value = hit ? (Array.isArray(hit.value) ? hit.value.join(" ") : hit.value) : "";
  return value.trim() || null;
}

function ChildRow({
  agentUid,
  entry,
  child,
  onSelect,
  onDelete,
}: {
  agentUid: string;
  entry: ConfigFileInfo;
  child: Child;
  onSelect: () => void;
  onDelete?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const absPath = `${entry.path}/${child.relpath}`;
  const [open, reveal] = useFileActionItems(absPath);
  const description = useChildDescription(agentUid, entry.key, child.relpath);
  return (
    <li className="flex items-center border-b border-border-subtle pr-2 hover:bg-surface-hover">
      <button
        type="button"
        onClick={onSelect}
        className="flex h-10 min-w-0 flex-1 items-center gap-2.5 pl-4 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      >
        <FileText className="size-[15px] shrink-0 text-text-subtle" aria-hidden />
        <span className="shrink-0 font-mono text-xs text-text">{child.relpath}</span>
        {description ? (
          <span className="min-w-0 truncate text-xs text-text-muted">{description}</span>
        ) : null}
        <span className="ml-auto shrink-0 whitespace-nowrap pl-2 text-xs text-text-subtle">
          {formatBytes(child.size)}
          {child.modified_at ? ` · ${shortDay(child.modified_at, i18n.language)}` : ""}
        </span>
      </button>
      <ActionMenu
        label={t("agents.configTab.moreFor", { name: child.relpath })}
        actions={[
          { key: "open", label: t("agents.configTab.openFile"), onSelect: open.onClick },
          { key: "reveal", label: reveal.label, onSelect: reveal.onClick },
          ...(onDelete
            ? [
                {
                  key: "delete",
                  label: t("agents.configTab.deleteFile"),
                  destructive: true,
                  separated: true,
                  onSelect: onDelete,
                },
              ]
            : []),
        ]}
      />
    </li>
  );
}

export function ConfigDirectoryPane({
  agentUid,
  entry,
  description,
  onSelectChild,
  onNewFile,
  onDeleteChild,
}: {
  agentUid: string;
  entry: ConfigFileInfo;
  description?: string | null;
  onSelectChild: (relpath: string) => void;
  /** Opens the New file dialog (board 2.1.47). */
  onNewFile?: () => void;
  /** Asks before deleting one of its files (board 2.1.48). */
  onDeleteChild?: (relpath: string) => void;
}) {
  const { t } = useTranslation();
  const children = entry.files ?? [];
  return (
    <>
      <ViewerToolbar path={`${abbreviateHomePath(entry.path)}/`}>
        {onNewFile ? (
          <Button variant="outline" size="sm" onClick={onNewFile}>
            <FilePlus aria-hidden /> {t("agents.configTab.newFile")}
          </Button>
        ) : null}
      </ViewerToolbar>

      {children.length === 0 ? (
        <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-muted">
          {t("agents.config.emptyDir")}
        </div>
      ) : (
        <ul className="min-h-0 flex-1 overflow-auto px-3">
          {children.map((c) => (
            <ChildRow
              key={c.relpath}
              agentUid={agentUid}
              entry={entry}
              child={c}
              onSelect={() => onSelectChild(c.relpath)}
              onDelete={onDeleteChild ? () => onDeleteChild(c.relpath) : undefined}
            />
          ))}
        </ul>
      )}

      <p className="flex h-[30px] shrink-0 items-center gap-2.5 border-t border-border-subtle px-3 text-xs text-text-muted">
        <span>{t("agents.configTab.folder")}</span>
        <span aria-hidden className="text-border">
          ·
        </span>
        <span className="truncate">
          {[description, t("agents.configTab.directoryHint")].filter(Boolean).join(" ")}
        </span>
      </p>
    </>
  );
}
