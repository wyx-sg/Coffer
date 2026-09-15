// frontend/src/pages/ProviderDetailPage.tsx
// Per-connection detail page (mirrors McpServerDetailPage): the shared
// PageHeader carrying back link + name + state badges + Edit/Delete/reach, then
// the body in two tabs (as on the agent detail page) — Overview, the read-only
// Configuration card the Edit dialog owns every change of, and Models, the
// table deciding which of the endpoint's models this connection offers at all.
// The open tab lives in the URL (`?tab=models`) so a refresh, a deep link or
// the back button lands on the same tab (agents/frontend.md §3).
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Boxes } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ProviderConfigCard } from "@/components/settings/ProviderConfigCard";
import { ProviderDetailHeader } from "@/components/settings/ProviderDetailHeader";
import { ProviderModelsTable } from "@/components/settings/ProviderModelsTable";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { useDeleteProvider, useProvider } from "@/lib/hooks/useProviders";

const TABS = ["overview", "models"] as const;
type Tab = (typeof TABS)[number];

export function ProviderDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: provider, isPending, error } = useProvider(name);
  const del = useDeleteProvider();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const back = { to: "/model-providers", label: t("settings.connections.detail.back") };
  const rawTab = searchParams.get("tab");
  const tab: Tab = TABS.includes(rawTab as Tab) ? (rawTab as Tab) : "overview";
  const setTab = (next: string) =>
    setSearchParams(next === "overview" ? {} : { tab: next }, { replace: true });

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-48" />} />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (error || !provider) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={name} />
        <EmptyState
          icon={Boxes}
          title={t("settings.connections.detail.notFound")}
          description={error ? translateApiError(t, error) : undefined}
          action={
            <Button asChild variant="outline">
              <Link to="/model-providers">
                <ArrowLeft className="mr-1.5 size-4" aria-hidden />
                {t("settings.connections.detail.back")}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ProviderDetailHeader
        provider={provider}
        deletePending={del.isPending}
        onDeleteClick={() => setDeleteOpen(true)}
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("settings.connections.detail.tabOverview")}</TabsTrigger>
          <TabsTrigger value="models">{t("settings.connections.detail.models")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-6">
          <ProviderConfigCard provider={provider} />
        </TabsContent>

        <TabsContent value="models" className="pt-6">
          <ProviderModelsTable provider={provider} />
        </TabsContent>
      </Tabs>

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
