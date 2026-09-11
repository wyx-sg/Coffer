// frontend/src/components/settings/ProviderDetailHeader.tsx
// Header of the connection detail page (mirrors McpServerDetailHeader): the
// name, the connection's type + state badges, and the two actions that change
// the connection itself — Edit (the existing ProviderForm, in a dialog owned
// here so the page file stays lean) and Delete (confirmed by the page). The
// description sits in the Configuration card rather than here, so it is stated
// exactly once.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Cpu, Pencil, Trash2 } from "lucide-react";

import { ProviderForm } from "@/components/settings/ProviderForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { Provider } from "@/lib/api/providers";
import { useUpdateProvider } from "@/lib/hooks/useProviders";

export function ProviderDetailHeader({
  provider,
  onDeleteClick,
  deletePending,
}: {
  provider: Provider;
  onDeleteClick: () => void;
  deletePending: boolean;
}) {
  const { t } = useTranslation();
  const update = useUpdateProvider();
  const [editOpen, setEditOpen] = useState(false);

  const closeEdit = () => {
    setEditOpen(false);
    update.reset();
  };

  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl tracking-tight">{provider.name}</h1>
          <Badge variant="secondary">{provider.protocol}</Badge>
          {provider.is_active ? (
            <Badge className="gap-1">
              <Check className="size-3" />
              {t("settings.connections.active")}
            </Badge>
          ) : null}
          {provider.internal_default ? (
            <Badge variant="outline" className="gap-1">
              <Cpu className="size-3" />
              {t("settings.connections.internalEngine")}
            </Badge>
          ) : null}
          <Badge variant="outline">
            {provider.enabled ? t("common.enabled") : t("common.disabled")}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
            <Pencil className="mr-1.5 size-3.5" /> {t("common.edit")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onDeleteClick}
            disabled={deletePending}
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
          </Button>
        </div>
      </div>
      <Dialog open={editOpen} onOpenChange={(open) => !open && closeEdit()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.connections.editTitle")}</DialogTitle>
          </DialogHeader>
          <ProviderForm
            initial={provider}
            submitError={update.error}
            pending={update.isPending}
            onCancel={closeEdit}
            onSubmit={() => {}}
            onUpdate={async (patch) => {
              await update.mutateAsync({ name: provider.name, patch });
              closeEdit();
            }}
          />
        </DialogContent>
      </Dialog>
    </header>
  );
}
