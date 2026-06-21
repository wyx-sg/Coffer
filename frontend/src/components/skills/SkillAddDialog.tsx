// frontend/src/components/skills/SkillAddDialog.tsx
// "Add skill" dialog: imports a local AgentSkills-standard folder from disk.
// On success the skills query is invalidated and the dialog closes.
// On 409 (RESOURCE_ALREADY_EXISTS) the UI surfaces an inline confirm to
// retry with overwrite: true — the explicit confirm IS the flag.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FolderPicker } from "@/components/agents/FolderPicker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useImportSkill } from "@/lib/hooks/useSkills";

export function SkillAddDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();

  const close = () => {
    onCreated();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("skills.add")}</DialogTitle>
          <DialogDescription>{t("skills.addSubtitle")}</DialogDescription>
        </DialogHeader>
        <LocalImportTab onSuccess={close} onCancel={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function LocalImportTab({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const importSkill = useImportSkill();
  const [path, setPath] = useState("");
  // When a 409 conflict is returned, we store the conflicting skill name here
  // to surface the replace-confirm UI. Cleared whenever the path changes.
  const [conflictName, setConflictName] = useState<string | null>(null);

  const handlePathChange = (value: string) => {
    setPath(value);
    setConflictName(null);
    importSkill.reset();
  };

  const runImport = async (overwrite?: boolean) => {
    try {
      await importSkill.mutateAsync({ path, ...(overwrite ? { overwrite: true } : {}) });
      onSuccess();
    } catch (err) {
      if (err instanceof ApiError && err.code === "RESOURCE_ALREADY_EXISTS") {
        // Derive skill name from the last path segment (best-effort for the UI label).
        const name = path.split(/[/\\]/).filter(Boolean).pop() ?? path;
        setConflictName(name);
      }
      // Other errors are surfaced inline via importSkill.error below.
    }
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void runImport();
      }}
      className="space-y-3"
    >
      <div className="space-y-1">
        <label htmlFor="skill-import-path" className="block text-sm">
          {t("skills.path")}
        </label>
        <div className="flex items-center gap-2">
          <input
            id="skill-import-path"
            className="block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
            required
            value={path}
            onChange={(e) => handlePathChange(e.target.value)}
            placeholder="/Users/me/.claude/skills/my-skill"
          />
          <FolderPicker value={path || null} onChange={handlePathChange} />
        </div>
      </div>
      {conflictName ? (
        <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-700 dark:bg-amber-950">
          <p className="font-medium text-amber-900 dark:text-amber-200">
            {t("skills.importConflictTitle", { name: conflictName })}
          </p>
          <div className="mt-2 flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setConflictName(null);
                importSkill.reset();
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setConflictName(null);
                void runImport(true);
              }}
              disabled={importSkill.isPending}
            >
              {importSkill.isPending ? t("common.saving") : t("skills.importReplace")}
            </Button>
          </div>
        </div>
      ) : importSkill.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, importSkill.error)}</p>
      ) : null}
      {!conflictName && (
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={importSkill.isPending}>
            {importSkill.isPending ? t("common.saving") : t("skills.import")}
          </Button>
        </div>
      )}
    </form>
  );
}
