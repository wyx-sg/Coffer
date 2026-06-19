// frontend/src/kinds/memory/MemoryRenameDialog.tsx
// Set or clear a memory store's display label (spec 007 FR-017c). Gives a store
// whose originating folder was never recorded a readable name instead of the
// opaque project-<ULID>. Clearing reverts to the project_root-derived / fallback
// name. Writes go through PATCH /memory_stores/{name}/label (the api helper).
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
import { renameMemoryStore } from "./api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  store: string;
  currentLabel: string | null;
}

export function MemoryRenameDialog({ open, onOpenChange, store, currentLabel }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [value, setValue] = useState(currentLabel ?? "");

  // Re-seed the field each time the dialog opens (the label may have changed).
  useEffect(() => {
    if (open) setValue(currentLabel ?? "");
  }, [open, currentLabel]);

  const rename = useMutation({
    mutationFn: (label: string | null) => renameMemoryStore(store, label),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-store", store] });
      void qc.invalidateQueries({ queryKey: ["memory-stores"] });
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
          <DialogTitle>{t("memory.rename.title")}</DialogTitle>
          <DialogDescription>{t("memory.rename.description")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            rename.mutate(trimmed || null);
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="memory-rename">{t("memory.rename.label")}</Label>
            <Input
              id="memory-rename"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={t("memory.rename.placeholder")}
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
                {t("memory.rename.clear")}
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
