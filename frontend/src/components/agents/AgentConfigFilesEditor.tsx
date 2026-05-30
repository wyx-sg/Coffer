// frontend/src/components/agents/AgentConfigFilesEditor.tsx — spec 004.
// Two-pane config editor for one agent: a left "tree" of the curated, editable
// config files (the allowlist — credential and machine-state files are
// deliberately excluded), and a right pane that shows the selected file in an
// editable textarea with a Save control. Saving writes atomically and keeps a
// `.bak` of the prior content; malformed JSON/TOML is rejected server-side and
// the on-disk file is left unchanged. A dependency-free find/replace bar
// (toggled by a button) operates on the editable content.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Search } from "lucide-react";

import { ConfigFindReplaceBar } from "@/components/agents/ConfigFindReplaceBar";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import {
  useAgentConfigFile,
  useAgentConfigFiles,
  useSaveAgentConfigFile,
} from "@/lib/hooks/useAgents";
import { cn } from "@/lib/utils";

export function AgentConfigFilesEditor({ name }: { name: string }) {
  const { t } = useTranslation();
  const files = useAgentConfigFiles(name);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const file = useAgentConfigFile(name, selectedKey);
  const save = useSaveAgentConfigFile(name);
  const selectedInfo = (files.data ?? []).find((f) => f.key === selectedKey);
  // List the full curated allowlist (FR-014 / User Story 7), including
  // not-yet-created files: the user can open one — it reads as empty without
  // being created — edit, and save to create it. Absent files are dimmed.
  const allFiles = files.data ?? [];

  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showFind, setShowFind] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Seed (and re-seed) the draft from the fetched content whenever the loaded
  // file changes, unless the user already has unsaved edits in flight.
  const fetched = file.data?.content ?? "";
  useEffect(() => {
    if (!dirty) setDraft(fetched);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetched, selectedKey]);

  function selectFile(key: string) {
    setSelectedKey(key);
    setDirty(false);
    setSaved(false);
    save.reset();
  }

  function updateDraft(next: string) {
    setDraft(next);
    setDirty(true);
    setSaved(false);
  }

  function onSave() {
    if (!selectedKey) return;
    save.mutate(
      { key: selectedKey, content: draft },
      {
        onSuccess: () => {
          setDirty(false);
          setSaved(true);
        },
      },
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
      {/* Left: the config-file tree (existing files only). */}
      <div className="space-y-1">
        <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("agents.config.files")}
        </p>
        {files.isPending ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : files.error ? (
          <p className="px-1 text-sm text-destructive">{translateApiError(t, files.error)}</p>
        ) : allFiles.length === 0 ? (
          <p className="px-1 text-sm text-muted-foreground">{t("agents.config.none")}</p>
        ) : (
          <ul className="space-y-0.5">
            {allFiles.map((f) => (
              <li key={f.key}>
                <button
                  type="button"
                  onClick={() => selectFile(f.key)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                    selectedKey === f.key
                      ? "bg-primary/10 text-primary"
                      : "hover:bg-secondary hover:text-foreground",
                    !f.exists && selectedKey !== f.key && "opacity-55",
                  )}
                >
                  <FileText className="size-4 shrink-0 opacity-70" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{f.display_name}</span>
                    <span className="block truncate font-mono text-[11px] text-muted-foreground">
                      {f.path}
                    </span>
                  </span>
                  {!f.exists ? (
                    <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
                      {t("agents.config.notCreated")}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Right: editable view of the selected file. */}
      <div className="min-w-0">
        {selectedKey ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-xs text-muted-foreground">
                {selectedInfo?.path ?? selectedKey}
              </span>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {file.data?.format ?? selectedInfo?.format}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-pressed={showFind}
                  onClick={() => setShowFind((v) => !v)}
                >
                  <Search className="mr-1 size-3.5" />
                  {t("agents.config.find.toggle")}
                </Button>
              </div>
            </div>

            {showFind ? (
              <ConfigFindReplaceBar
                content={draft}
                onContentChange={updateDraft}
                textareaRef={textareaRef}
              />
            ) : null}

            <textarea
              ref={textareaRef}
              aria-label={t("agents.config.editorLabel", { key: selectedKey })}
              className="h-80 w-full resize-none rounded border bg-background p-2 font-mono text-xs text-foreground"
              value={file.isPending ? "" : draft}
              onChange={(e) => updateDraft(e.target.value)}
              spellCheck={false}
            />

            {save.error ? (
              <p role="alert" className="text-xs text-destructive">
                {translateApiError(t, save.error)}
              </p>
            ) : saved ? (
              <p className="text-xs text-muted-foreground">{t("agents.config.savedWithBackup")}</p>
            ) : null}

            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={onSave}
                disabled={!dirty || save.isPending || file.isPending}
              >
                {save.isPending ? t("common.saving") : t("agents.config.save")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
            {t("agents.config.selectFile")}
          </div>
        )}
      </div>
    </div>
  );
}
