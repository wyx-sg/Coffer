// frontend/src/components/agents/ConfigEditorPane.tsx — spec 004.
// Right pane of the agent config editor: path/format header, stale-write and
// memory-block banners, the optional find/replace bar, the editable textarea,
// and the Save row. Extracted from AgentConfigFilesEditor to keep that file
// inside the component size cap; all state stays in the parent.
import type { MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import { Info, Search, Trash2, TriangleAlert } from "lucide-react";

import { ConfigFindReplaceBar } from "@/components/agents/ConfigFindReplaceBar";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";

export interface ConfigEditorPaneProps {
  /** Full path shown in the header (file path, or path/relpath for a child). */
  pathLabel: string;
  /** One-line "what is this file for" copy, shown under the path. */
  description?: string | null;
  formatLabel: string | undefined;
  /** i18n key parameter for the textarea aria-label. */
  editorKey: string;
  draft: string;
  /** True while the content query is loading (textarea renders empty). */
  loading: boolean;
  onDraftChange: (next: string) => void;
  textareaRef: MutableRefObject<HTMLTextAreaElement | null>;
  showFind: boolean;
  onToggleFind: () => void;
  /** Non-null when a directory child is selected — shows the Delete action. */
  onDeleteChild: (() => void) | null;
  stale: boolean;
  onReloadStale: () => void;
  memoryBlock: boolean;
  saveError: unknown;
  saved: boolean;
  savePending: boolean;
  saveDisabled: boolean;
  onSave: () => void;
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
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-xs text-muted-foreground">{props.formatLabel}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-pressed={props.showFind}
            onClick={props.onToggleFind}
          >
            <Search className="mr-1 size-3.5" />
            {t("agents.config.find.toggle")}
          </Button>
          {props.onDeleteChild ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="text-destructive"
              onClick={props.onDeleteChild}
            >
              <Trash2 className="mr-1 size-3.5" />
              {t("agents.config.deleteChild")}
            </Button>
          ) : null}
        </div>
      </div>

      {props.stale ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-2 rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-700 dark:text-amber-400"
        >
          <span className="flex items-center gap-1.5">
            <TriangleAlert className="size-3.5 shrink-0" />
            {t("agents.config.staleBanner")}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={props.onReloadStale}>
            {t("agents.config.reload")}
          </Button>
        </div>
      ) : null}

      {props.memoryBlock ? (
        <div className="flex items-center gap-1.5 rounded border border-sky-500/50 bg-sky-500/10 px-2 py-1.5 text-xs text-sky-700 dark:text-sky-400">
          <Info className="size-3.5 shrink-0" />
          {t("agents.config.memoryBlockNotice")}
        </div>
      ) : null}

      {props.showFind ? (
        <ConfigFindReplaceBar
          content={props.draft}
          onContentChange={props.onDraftChange}
          textareaRef={props.textareaRef}
        />
      ) : null}

      <textarea
        ref={props.textareaRef}
        aria-label={t("agents.config.editorLabel", { key: props.editorKey })}
        className="h-80 w-full resize-none rounded border bg-background p-2 font-mono text-xs text-foreground"
        value={props.loading ? "" : props.draft}
        onChange={(e) => props.onDraftChange(e.target.value)}
        spellCheck={false}
      />

      {props.saveError && !props.stale ? (
        <p role="alert" className="text-xs text-destructive">
          {translateApiError(t, props.saveError)}
        </p>
      ) : props.saved ? (
        <p className="text-xs text-muted-foreground">{t("agents.config.savedWithBackup")}</p>
      ) : null}

      <div className="flex items-center gap-2">
        <Button type="button" size="sm" onClick={props.onSave} disabled={props.saveDisabled}>
          {props.savePending ? t("common.saving") : t("agents.config.save")}
        </Button>
      </div>
    </div>
  );
}
