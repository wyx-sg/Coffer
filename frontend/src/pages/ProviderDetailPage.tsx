// frontend/src/pages/ProviderDetailPage.tsx
// Per-connection detail page (mirrors McpServerDetailPage): a back link, a
// header carrying the name + state badges + Edit/Delete, then the body —
// Configuration (read-only; the Edit dialog owns every change) and Models (which
// of the endpoint's models this connection offers at all).
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";

import { ProviderConfigCard } from "@/components/settings/ProviderConfigCard";
import { ProviderDetailHeader } from "@/components/settings/ProviderDetailHeader";
import { ProviderModelsCard } from "@/components/settings/ProviderModelsCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import { useDeleteProvider, useProvider } from "@/lib/hooks/useProviders";

export function ProviderDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: provider, isPending, error } = useProvider(name);
  const del = useDeleteProvider();
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (error || !provider) {
    return (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">
            {t("settings.connections.detail.notFound")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {error ? translateApiError(t, error) : t("settings.connections.detail.notFound")}
          </p>
          <Button variant="link" onClick={() => navigate("/model-providers")} className="-ml-2">
            <ArrowLeft className="mr-1 size-4" />
            {t("settings.connections.detail.back")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="-ml-2 flex flex-wrap items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/model-providers")}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1.5 size-4" /> {t("settings.connections.detail.back")}
        </Button>
      </div>

      <ProviderDetailHeader
        provider={provider}
        deletePending={del.isPending}
        onDeleteClick={() => setDeleteOpen(true)}
      />

      <ProviderConfigCard provider={provider} />
      <ProviderModelsCard provider={provider} />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("settings.connections.deleteTitle")}
        description={t("settings.connections.deleteConfirm", { name: provider.name })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        onConfirm={() =>
          del.mutate(provider.name, {
            onSuccess: () => {
              setDeleteOpen(false);
              navigate("/model-providers");
            },
          })
        }
      />
    </div>
  );
}
