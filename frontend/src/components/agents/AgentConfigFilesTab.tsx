// frontend/src/components/agents/AgentConfigFilesTab.tsx — spec agent-registry
// "Open config files in an external editor or reveal them" and
// "Preview an agent's config file read-only".
// The agent detail page's Config files tab: ONE bordered surface with a
// draggable divider — the curated config-file allowlist as a tree on the left
// (ConfigFileTree; the directory entry agents/ expands to its files, a file not
// created yet is greyed and cannot be opened) and the selected file read-only
// on the right (the shared viewer: its path and size, Open in editor, Reveal in
// Finder). Coffer edits nothing: a config file is changed in the person's own
// editor, or by their agent. The selected file is in the URL (`?file=`), the
// first existing file by default. Secret and machine-state files are not on the
// allowlist, so never here.
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import {
  ConfigFileTree,
  openableSelections,
  selectionFromParam,
  selectionToParam,
  type ConfigSelection,
} from "@/components/agents/ConfigFileTree";
import { FileBrowserFrame } from "@/components/files/FileBrowserFrame";
import { FileTreePanel } from "@/components/files/FileTree";
import { ReadOnlyFile } from "@/components/files/ReadOnlyFile";
import { LoadError } from "@/components/LoadError";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useFsActions } from "@/lib/fsActions";
import { useAgentConfigFileContent, useAgentConfigFiles } from "@/lib/hooks/useAgents";

// The card's own bounds: the tree may shrink to 160px, the open file keeps 320px.
const TREE_MIN = 160;
const FILE_MIN = 320;

const QUIET = "flex min-h-0 flex-1 items-center justify-center text-sm text-text-muted";

function OpenConfigFile({
  agentUid,
  selection,
  path,
}: {
  agentUid: string;
  selection: ConfigSelection;
  path: string;
}) {
  const query = useAgentConfigFileContent(agentUid, selection.key, selection.child ?? "");
  return (
    <ReadOnlyFile
      path={selection.child ?? baseName(path)}
      displayPath={abbreviateHomePath(query.data?.abs_path ?? path)}
      query={query}
      reveal
    />
  );
}

export function AgentConfigFilesTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  const agentName = agentTypeLabel(agent.type);
  const files = useAgentConfigFiles(agent.uid);
  const [params, setParams] = useSearchParams();

  const openable = files.data ? openableSelections(files.data) : [];
  const wanted = selectionFromParam(params.get("file"));
  const selected =
    openable.find((s) => s.key === wanted?.key && s.child === wanted?.child) ?? openable[0] ?? null;
  const select = (sel: ConfigSelection) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("file", selectionToParam(sel));
        return next;
      },
      { replace: true },
    );

  // The open file's path on disk, from the listing, until its content answers.
  let openPath = "";
  if (selected && files.data) {
    const entry = files.data.find((f) => f.key === selected.key);
    openPath =
      (selected.child
        ? entry?.files?.find((c) => c.relpath === selected.child)?.path
        : entry?.path) ?? "";
  }

  let list;
  if (files.error) {
    list = <LoadError className="px-2" error={files.error} onRetry={() => void files.refetch()} />;
  } else if (files.isPending) {
    list = <Skeleton className="h-24 w-full" aria-busy />;
  } else if (files.data.length === 0) {
    list = <p className="px-2 text-sm text-text-muted">{t("agents.config.none")}</p>;
  } else {
    list = (
      <ConfigFileTree
        files={files.data}
        agentName={agentName}
        selected={selected}
        onSelect={select}
      />
    );
  }

  return (
    <FileBrowserFrame
      sideWidth={260}
      resizable={{
        storageKey: "agent-config-files",
        label: t("splitView.resizeList"),
        listMinWidth: TREE_MIN,
        detailMinWidth: FILE_MIN,
      }}
      side={
        <FileTreePanel
          title={t("agents.configTab.title", { agent: agentName })}
          action={
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-text-muted"
              aria-label={t("fileActions.reveal")}
              title={t("fileActions.reveal")}
              onClick={() =>
                void reveal(agent.config_dir).catch(() =>
                  toast.error(t("fileActions.revealFailed")),
                )
              }
            >
              <FolderOpen aria-hidden />
            </Button>
          }
        >
          {list}
        </FileTreePanel>
      }
      main={
        selected ? (
          <div key={selectionToParam(selected)} className="flex min-h-0 min-w-0 flex-1 flex-col">
            <OpenConfigFile agentUid={agent.uid} selection={selected} path={openPath} />
          </div>
        ) : (
          <div className={QUIET}>{t("agents.config.selectFile")}</div>
        )
      }
    />
  );
}
