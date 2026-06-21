// frontend/src/components/agents/ConfigEditorPane.tsx — spec 004.
// Right pane of the agent config viewer: path/format header, the external-file
// action bar (open-in-editor / reveal), an optional read-only
// managed-block annotation, and a read-only preview of the file's content.
// Config files are edited in the user's own editor, not in-app — this pane
// never mutates. Extracted from AgentConfigFilesEditor to keep that file inside
// the component size cap; all state stays in the parent.
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { FileActions } from "@/components/FileActions";

export interface ConfigEditorPaneProps {
  /** Full path shown in the header (file path, or path/relpath for a child). */
  pathLabel: string;
  /** Absolute on-disk path of the file (for the external-editor actions). */
  filePath?: string;
  /** Absolute on-disk path of its containing folder (enables folder actions). */
  folderPath?: string;
  /** One-line "what is this file for" copy, shown under the path. */
  description?: string | null;
  formatLabel: string | undefined;
  /** i18n key parameter for the preview aria-label. */
  editorKey: string;
  /** The file's current on-disk content (read-only). */
  content: string;
  /** True while the content query is loading (preview renders empty). */
  loading: boolean;
  /** True when the file carries a Coffer memory-projection block. */
  memoryBlock: boolean;
}

export function ConfigEditorPane(props: ConfigEditorPaneProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-xs text-muted-foreground">
            {props.pathLabel}
          </span>
          {props.description ? (
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {props.description}
            </span>
          ) : null}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">{props.formatLabel}</span>
      </div>

      {props.filePath ? (
        <FileActions filePath={props.filePath} folderPath={props.folderPath} />
      ) : null}

      {props.memoryBlock ? (
        <div className="flex items-center gap-1.5 rounded border border-sky-500/50 bg-sky-500/10 px-2 py-1.5 text-xs text-sky-700">
          <Info className="size-3.5 shrink-0" />
          {t("agents.config.memoryBlockNotice")}
        </div>
      ) : null}

      <pre
        aria-label={t("agents.config.editorLabel", { key: props.editorKey })}
        className="h-80 w-full overflow-auto whitespace-pre-wrap break-words rounded border bg-muted/30 p-2 font-mono text-xs text-foreground"
      >
        {props.loading ? "" : props.content}
      </pre>
    </div>
  );
}
