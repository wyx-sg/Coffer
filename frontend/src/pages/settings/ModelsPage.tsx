// pages/settings/ModelsPage.tsx — lists, adds, edits, deletes model configs.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Cpu, Plus, Pencil, Trash2, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useModels, useCreateModel, useUpdateModel, useDeleteModel } from "@/lib/hooks/useModels";
import { ModelForm } from "@/components/settings/ModelForm";
import { EmbeddingSettings } from "./EmbeddingSettings";
import { translateApiError } from "@/lib/api/errors";
import type { Model } from "@/lib/api/models";

export function ModelsPage() {
  const { t } = useTranslation();
  const { data: models = [], isPending, error } = useModels();
  const createModel = useCreateModel();
  const updateModel = useUpdateModel();
  const deleteModel = useDeleteModel();

  const [editTarget, setEditTarget] = useState<Model | null | "new">(null);
  // Delete is destructive and irreversible, so it goes through a styled
  // confirmation dialog rather than firing on a single click.
  const [deleteTarget, setDeleteTarget] = useState<Model | null>(null);

  const handleClose = () => {
    setEditTarget(null);
    // m4: Reset mutation state so a stale error from a prior failed attempt
    // is not shown the next time the dialog is opened.
    createModel.reset();
    updateModel.reset();
  };

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-6">{t("common.loading")}</CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardContent className="py-6 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="size-5 text-primary" strokeWidth={1.5} />
              {t("settings.models.llmTitle")}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">{t("settings.models.subtitle")}</p>
          </div>
          <Button size="sm" onClick={() => setEditTarget("new")}>
            <Plus className="mr-1.5 size-4" />
            {t("settings.models.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {models.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              {t("settings.models.empty")}
            </div>
          ) : (
            <div className="space-y-2">
              {models.map((m) => (
                <Card key={m.id} className="paper-card">
                  <CardContent className="flex items-center gap-3 py-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">{m.display_name}</span>
                        {m.is_default && (
                          <Star
                            className="size-3.5 shrink-0 fill-amber-400 text-amber-400"
                            aria-label={t("settings.models.default")}
                          />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {m.provider} · {m.model}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="size-7 p-0"
                      onClick={() => setEditTarget(m)}
                      aria-label={t("common.edit")}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="size-7 p-0 hover:text-destructive"
                      onClick={() => setDeleteTarget(m)}
                      disabled={deleteModel.isPending}
                      aria-label={t("common.delete")}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={editTarget !== null} onOpenChange={(open) => !open && handleClose()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editTarget === "new"
                ? t("settings.models.addTitle")
                : t("settings.models.editTitle")}
            </DialogTitle>
          </DialogHeader>
          {editTarget !== null && (
            <ModelForm
              existing={editTarget !== "new" ? editTarget : undefined}
              submitError={createModel.error ?? updateModel.error}
              onCancel={handleClose}
              onSubmit={async (values) => {
                if (editTarget === "new") {
                  await createModel.mutateAsync(
                    values as Parameters<typeof createModel.mutateAsync>[0],
                  );
                } else {
                  await updateModel.mutateAsync({ id: editTarget.id, patch: values });
                }
                handleClose();
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={t("settings.models.deleteTitle")}
        description={t("settings.models.deleteConfirm", {
          name: deleteTarget?.display_name ?? "",
        })}
        confirmLabel={deleteModel.isPending ? t("common.deleting") : t("common.delete")}
        pending={deleteModel.isPending}
        onConfirm={() => {
          if (deleteTarget) {
            deleteModel.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
      />

      {/* Embedding is model configuration too — its own boxed card, parallel
          to the LLM card above. */}
      <EmbeddingSettings />
    </div>
  );
}
