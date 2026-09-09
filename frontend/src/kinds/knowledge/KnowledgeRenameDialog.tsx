// frontend/src/kinds/knowledge/KnowledgeRenameDialog.tsx
// Set or clear a knowledge scope's display label. Gives a scope whose
// originating folder was never recorded a readable name instead of the opaque
// project-<ULID>. Clearing reverts to the project_root-derived / fallback name.
// Writes go through PATCH /knowledge/{scope}/label (the api helper).
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import { renameScope } from "./api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scope: string;
  currentLabel: string | null;
}

export function KnowledgeRenameDialog({ open, onOpenChange, scope, currentLabel }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [value, setValue] = useState(currentLabel ?? "");

  // Re-seed the field each time the dialog opens (the label may have changed).
  useEffect(() => {
    if (open) setValue(currentLabel ?? "");
  }, [open, currentLabel]);

  const rename = useMutation({
    mutationFn: (label: string | null) => renameScope(scope, label),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-scope", scope] });
      void qc.invalidateQueries({ queryKey: ["knowledge-scopes"] });
      onOpenChange(false);
    },
  });

  const trimmed = value.trim();
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) rename.reset();
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("knowledge.rename.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.rename.description")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            rename.mutate(trimmed || null);
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="knowledge-rename">{t("knowledge.rename.label")}</Label>
            <Input
              id="knowledge-rename"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={t("knowledge.rename.placeholder")}
              maxLength={200}
              autoFocus
            />
          </div>
          {rename.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, rename.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            {currentLabel ? (
              <Button
                type="button"
                variant="outline"
                disabled={rename.isPending}
                onClick={() => rename.mutate(null)}
              >
                {t("knowledge.rename.clear")}
              </Button>
            ) : null}
            <Button type="submit" disabled={rename.isPending || trimmed === (currentLabel ?? "")}>
              {rename.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
