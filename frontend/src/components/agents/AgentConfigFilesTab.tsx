// frontend/src/components/agents/AgentConfigFilesTab.tsx — spec agent-registry
// "Open config files in an external editor or reveal them" and
// "Preview an agent's config file read-only".
// The agent detail page's Config files tab: the curated config-file allowlist as
// a read-only list. Each file is a row — its name, its folder, its size and when
// it changed — with Open in editor and Reveal in Finder; a directory entry
// (Claude Code's agents/) lists its files under it, each with the same two. A
// file's name opens its read-only preview in a dialog. A file not created yet
// reads "Not created", has no preview and offers Reveal on its folder only,
// because opening creates nothing. Coffer edits nothing: a config file is
// changed in the person's own editor, or by their agent. Secret and
// machine-state files are not on the allowlist, so never here.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import {
  AgentConfigFilePreviewDialog,
  type ConfigFileTarget,
} from "@/components/agents/AgentConfigFilePreviewDialog";
import { LoadError } from "@/components/LoadError";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut, ConfigFileInfo } from "@/lib/api/agents";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useAgentConfigFiles } from "@/lib/hooks/useAgents";
import { cn, formatBytes, formatDateTime } from "@/lib/utils";

// Keys with a description under `agents.config.desc.<key>`. Listing them keeps
// an unknown/new key from rendering a raw i18n string.
const DESCRIBED_KEYS = new Set([
  "settings",
  "settings_local",
  "global",
  "instructions",
  "subagents",
  "config",
  "hooks",
]);

type Child = NonNullable<ConfigFileInfo["files"]>[number];

interface RowProps {
  name: string;
  /** Second line under the name: what the file is for. */
  description?: string | null;
  /** The folder the file sits in, as the row shows it. */
  folder: string;
  /** Size · modified, or null when the file is not created yet. */
  facts: { size: number | null; modifiedAt: string | null } | null;
  /** The absolute path Open and Reveal act on. */
  path: string;
  /** Where Reveal goes when `path` does not exist: its folder. */
  folderPath: string;
  /** Directories offer Reveal only. */
  openable?: boolean;
  child?: boolean;
  /** Set on a file that exists: its name opens this preview. */
  onPreview?: () => void;
}

function ConfigFileRow({
  name,
  description,
  folder,
  facts,
  path,
  folderPath,
  openable = true,
  child = false,
  onPreview,
}: RowProps) {
  const { t } = useTranslation();
  const [open, revealFile] = useFileActionItems(path);
  const [, revealFolder] = useFileActionItems(folderPath);
  const reveal = facts ? revealFile : revealFolder;
  return (
    <li
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-border-subtle py-2.5 pr-3 last:border-b-0",
        child ? "pl-9" : "pl-3",
      )}
    >
      <div className="min-w-0 flex-1 basis-60">
        {onPreview ? (
          <button
            type="button"
            className="block max-w-full truncate text-left font-mono text-sm text-text hover:text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            onClick={onPreview}
          >
            {name}
          </button>
        ) : (
          <div className="truncate font-mono text-sm text-text">{name}</div>
        )}
        {description ? <div className="text-xs text-text-muted">{description}</div> : null}
        <div className="truncate font-mono text-xs text-text-subtle" title={folderPath}>
          {folder}
        </div>
      </div>
      <div className="shrink-0 whitespace-nowrap text-xs text-text-muted">
        {facts
          ? [
              facts.size !== null ? formatBytes(facts.size) : null,
              facts.modifiedAt ? formatDateTime(facts.modifiedAt) : null,
            ]
              .filter(Boolean)
              .join(" · ")
          : t("agents.config.notCreated")}
      </div>
      <div className="flex shrink-0 gap-1.5">
        {facts && openable ? (
          <Button variant="outline" size="sm" onClick={open.onClick}>
            <open.icon aria-hidden /> {open.label}
          </Button>
        ) : null}
        <Button variant="outline" size="sm" onClick={reveal.onClick}>
          <reveal.icon aria-hidden /> {reveal.label}
        </Button>
      </div>
    </li>
  );
}

function EntryRows({
  entry,
  agentName,
  onPreview,
}: {
  entry: ConfigFileInfo;
  agentName: string;
  onPreview: (target: ConfigFileTarget) => void;
}) {
  const { t } = useTranslation();
  const isDir = entry.kind === "directory";
  const children: Child[] = entry.files ?? [];
  return (
    <>
      <ConfigFileRow
        name={isDir ? `${baseName(entry.path)}/` : baseName(entry.path)}
        description={
          DESCRIBED_KEYS.has(entry.key)
            ? t(`agents.config.desc.${entry.key}`, { agent: agentName })
            : null
        }
        folder={abbreviateHomePath(entry.folder_path)}
        facts={entry.exists ? { size: entry.size, modifiedAt: entry.modified_at } : null}
        path={entry.path}
        folderPath={entry.folder_path}
        openable={!isDir}
        onPreview={
          entry.exists && !isDir
            ? () => onPreview({ key: entry.key, name: baseName(entry.path), path: entry.path })
            : undefined
        }
      />
      {isDir && entry.exists && children.length === 0 ? (
        <li className="border-b border-border-subtle py-2 pl-9 text-xs text-text-muted">
          {t("agents.config.emptyDir")}
        </li>
      ) : null}
      {children.map((c) => (
        <ConfigFileRow
          key={c.relpath}
          child
          name={c.relpath}
          folder={abbreviateHomePath(entry.path)}
          facts={{ size: c.size, modifiedAt: c.modified_at }}
          path={c.path}
          folderPath={entry.path}
          onPreview={() =>
            onPreview({ key: entry.key, child: c.relpath, name: c.relpath, path: c.path })
          }
        />
      ))}
    </>
  );
}

export function AgentConfigFilesTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const agentName = agentTypeLabel(agent.type);
  const files = useAgentConfigFiles(agent.uid);
  const [previewing, setPreviewing] = useState<ConfigFileTarget | null>(null);
  const [, revealDir] = useFileActionItems(agent.config_dir);

  let body;
  if (files.error) {
    body = <LoadError error={files.error} onRetry={() => void files.refetch()} />;
  } else if (files.isPending) {
    body = <Skeleton className="h-40 w-full" aria-busy />;
  } else if (files.data.length === 0) {
    body = <p className="text-sm text-text-muted">{t("agents.config.none")}</p>;
  } else {
    body = (
      <ul className="overflow-hidden rounded-lg border border-border-subtle">
        {files.data.map((entry) => (
          <EntryRows
            key={entry.key}
            entry={entry}
            agentName={agentName}
            onPreview={setPreviewing}
          />
        ))}
      </ul>
    );
  }

  return (
    <Section
      title={t("agents.configTab.title", { agent: agentName })}
      as="h2"
      actions={
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={revealDir.label}
          title={revealDir.label}
          onClick={revealDir.onClick}
        >
          <FolderOpen aria-hidden />
        </Button>
      }
    >
      {body}
      <AgentConfigFilePreviewDialog
        agentUid={agent.uid}
        target={previewing}
        onClose={() => setPreviewing(null)}
      />
    </Section>
  );
}
