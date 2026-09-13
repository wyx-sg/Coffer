// frontend/src/components/settings/ProviderDetailHeader.tsx
// Header of the connection detail page (mirrors McpServerDetailHeader): the
// name, the connection's type + state badges, and the actions that change the
// connection itself — Edit (the existing ProviderForm, in a dialog owned
// here so the page file stays lean), Delete (confirmed by the page), and the
// shared ScopeControl, which is where enabled/disabled is both SHOWN and
// changed. It replaced a read-only badge: the list could flip a provider and its
// own page could not, and a badge next to the control would have stated the same
// state twice. `provider` declares no per-agent scope, so the control renders
// its two-segment Disabled/Enabled fallback. The description sits in the
// Configuration card rather than here, so it is stated exactly once.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check, Pencil, Trash2 } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { ProviderForm } from "@/components/settings/ProviderForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { Provider } from "@/lib/api/providers";
import { useRenameProvider, useUpdateProvider } from "@/lib/hooks/useProviders";

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
  const navigate = useNavigate();
  const update = useUpdateProvider();
  const rename = useRenameProvider();
  const [editOpen, setEditOpen] = useState(false);

  const closeEdit = () => {
    setEditOpen(false);
    update.reset();
    rename.reset();
  };

  /** Save the edit dialog. A changed NAME goes first and on its own route: a
   *  name is a label, not config, and one already taken must fail BEFORE any of
   *  this dialog's other edits land. The patch then addresses the connection by
   *  whatever name it now has, and the page follows it — this route IS the
   *  name, so staying put would leave the user on a URL that 404s. */
  const save = async (
    patch: Parameters<typeof update.mutateAsync>[0]["patch"],
    next: string | null,
  ) => {
    try {
      if (next) await rename.mutateAsync({ name: provider.name, newName: next });
      await update.mutateAsync({ name: next ?? provider.name, patch });
    } catch {
      // Swallowed deliberately: the failure is already the mutation's state,
      // which the dialog renders inline (and the hook toasts). Letting it
      // escape the form's submit handler would only be an unhandled rejection.
      return;
    }
    closeEdit();
    if (next) navigate(`/model-providers/${encodeURIComponent(next)}`, { replace: true });
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
          <ScopeControl kind="provider" name={provider.name} enabled={provider.enabled} />
        </div>
      </div>
      <Dialog open={editOpen} onOpenChange={(open) => !open && closeEdit()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.connections.editTitle")}</DialogTitle>
          </DialogHeader>
          <ProviderForm
            initial={provider}
            submitError={rename.error ?? update.error}
            pending={update.isPending || rename.isPending}
            onCancel={closeEdit}
            onSubmit={() => {}}
            onUpdate={save}
          />
        </DialogContent>
      </Dialog>
    </header>
  );
}
