// frontend/src/components/skills/SkillAddDialog.tsx
// "Add skill" dialog: imports a local AgentSkills-standard folder from disk.
// On success the skills query is invalidated and the dialog closes.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
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
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await importSkill.mutateAsync({ path });
          onSuccess();
        } catch {
          // Surfaced inline via importSkill.error below.
        }
      }}
      className="space-y-3"
    >
      <label className="block text-sm">
        {t("skills.path")}
        <input
          className="mt-1 block w-full rounded border bg-background px-2 py-1 font-mono text-xs"
          required
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="/Users/me/.claude/skills/my-skill"
        />
      </label>
      {importSkill.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, importSkill.error)}</p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={importSkill.isPending}>
          {importSkill.isPending ? t("common.saving") : t("skills.import")}
        </Button>
      </div>
    </form>
  );
}
