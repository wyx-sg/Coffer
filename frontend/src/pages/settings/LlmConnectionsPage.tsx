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
import { Boxes, Check, Cpu, Plus, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ProviderForm } from "@/components/settings/ProviderForm";
import {
  useProviders,
  useCreateProvider,
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
  const deleteProvider = useDeleteProvider();
  const activateProvider = useActivateProvider();
  const setInternalDefault = useSetInternalDefaultProvider();

  const [adding, setAdding] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null);

  const closeAdd = () => {
    setAdding(false);
    createProvider.reset();
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
                  <Card className="paper-card">
                    <CardContent className="flex items-center gap-3 py-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-sm font-medium">{p.name}</span>
                          {p.is_active && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                              <Check className="size-3" />
                              {t("settings.connections.active")}
                            </span>
                          )}
                          {p.internal_default && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2 py-0.5 text-xs text-amber-600">
                              <Cpu className="size-3" />
                              {t("settings.connections.internalDefault")}
                            </span>
                          )}
                        </div>
                        <p className="truncate text-xs text-muted-foreground">
                          {p.wire_format} · {p.model} · {p.base_url}
                        </p>
                      </div>
                      {/* Internal-engine selection: a star toggle, parallel to
                          the per-wire "Switch" but global and orthogonal. */}
                      <Button
                        variant="ghost"
                        size="sm"
                        className={
                          p.internal_default
                            ? "size-7 p-0 text-amber-500"
                            : "size-7 p-0 text-muted-foreground hover:text-amber-500"
                        }
                        disabled={p.internal_default || setInternalDefault.isPending}
                        onClick={() => setInternalDefault.mutate(p.name)}
                        aria-label={t("settings.connections.setInternalDefault", { name: p.name })}
                        title={t("settings.connections.setInternalDefault", { name: p.name })}
                      >
                        <Star
                          className={p.internal_default ? "size-4 fill-amber-400" : "size-4"}
                        />
                      </Button>
                      {/* Ollama is internal-only — never projected to an agent, so
                          it has no per-wire "Switch" action. */}
                      {p.wire_format !== "ollama" && !p.is_active && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={activateProvider.isPending}
                          onClick={() => activateProvider.mutate(p.name)}
                        >
                          {t("settings.connections.switch")}
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="size-7 p-0 hover:text-destructive"
                        onClick={() => setDeleteTarget(p)}
                        disabled={deleteProvider.isPending}
                        aria-label={t("common.delete")}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </CardContent>
                  </Card>
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
