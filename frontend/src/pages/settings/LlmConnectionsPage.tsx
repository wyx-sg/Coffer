// pages/settings/LlmConnectionsPage.tsx — the unified LLM-connection surface
// (spec 011). A connection = key + endpoint + wire + model; one configured key
// is usable by both agents (per-wire `activate`) and Coffer's internal engine
// (`internal_default`). This page is the connection library (add / delete /
// switch active) plus the Coffer-internal-engine selection. It shows ONLY
// connection (provider + model) info — never agent names; per-agent connection
// selection lives on the Agent detail → Overview tab. The Embedding card stays
// at the bottom.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Boxes, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ConnectionCard } from "@/components/settings/ConnectionCard";
import { ProviderForm } from "@/components/settings/ProviderForm";
import {
  useProviders,
  useCreateProvider,
  useUpdateProvider,
  useDeleteProvider,
  useActivateProvider,
  useSetInternalDefaultProvider,
} from "@/lib/hooks/useProviders";
import { translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { EmbeddingSettings } from "./EmbeddingSettings";

export function LlmConnectionsPage() {
  const { t } = useTranslation();
  const { data: providers = [], isPending, error } = useProviders();
  const createProvider = useCreateProvider();
  const updateProvider = useUpdateProvider();
  const deleteProvider = useDeleteProvider();
  const activateProvider = useActivateProvider();
  const setInternalDefault = useSetInternalDefaultProvider();

  const [adding, setAdding] = useState(false);
  const [editTarget, setEditTarget] = useState<Provider | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null);

  const closeAdd = () => {
    setAdding(false);
    createProvider.reset();
  };

  const closeEdit = () => {
    setEditTarget(null);
    updateProvider.reset();
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
              <Boxes className="size-5 text-primary" strokeWidth={1.5} />
              {t("settings.connections.title")}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("settings.connections.subtitle")}
            </p>
          </div>
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus className="mr-1.5 size-4" />
            {t("settings.connections.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {providers.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              {t("settings.connections.empty")}
            </div>
          ) : (
            <ul className="space-y-2">
              {providers.map((p) => (
                <li key={p.name}>
                  <ConnectionCard
                    provider={p}
                    internalPending={setInternalDefault.isPending}
                    activatePending={activateProvider.isPending}
                    deletePending={deleteProvider.isPending}
                    onSetInternalDefault={(name) => setInternalDefault.mutate(name)}
                    onActivate={(name) => activateProvider.mutate(name)}
                    onEdit={(prov) => setEditTarget(prov)}
                    onDelete={(prov) => setDeleteTarget(prov)}
                  />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Dialog open={adding} onOpenChange={(open) => !open && closeAdd()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.connections.addTitle")}</DialogTitle>
          </DialogHeader>
          <ProviderForm
            submitError={createProvider.error}
            pending={createProvider.isPending}
            onCancel={closeAdd}
            onSubmit={async (values) => {
              await createProvider.mutateAsync(values);
              closeAdd();
            }}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={editTarget !== null} onOpenChange={(open) => !open && closeEdit()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.connections.editTitle")}</DialogTitle>
          </DialogHeader>
          {editTarget && (
            <ProviderForm
              initial={editTarget}
              submitError={updateProvider.error}
              pending={updateProvider.isPending}
              onCancel={closeEdit}
              onSubmit={() => {}}
              onUpdate={async (patch) => {
                await updateProvider.mutateAsync({ name: editTarget.name, patch });
                closeEdit();
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={t("settings.connections.deleteTitle")}
        description={t("settings.connections.deleteConfirm", { name: deleteTarget?.name ?? "" })}
        confirmLabel={deleteProvider.isPending ? t("common.deleting") : t("common.delete")}
        pending={deleteProvider.isPending}
        onConfirm={() => {
          if (deleteTarget) {
            deleteProvider.mutate(deleteTarget.name, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
      />

      {/* Embedding is its own separate config (own shape with dimensions) — its
          own boxed card at the bottom, parallel to the connections card above. */}
      <EmbeddingSettings />
    </div>
  );
}
