// pages/ModelProvidersPage.tsx — the model-provider surface (spec provider-switching).
//
// A provider here is a credentialed endpoint: `{protocol, base_url,
// credential_ref}`. Which MODEL an agent runs on is still chosen at the point of
// use (the per-agent binding on Agent detail → Overview) — this page manages
// vendor endpoints and their keys; the connection's own CURATED model set (which
// of the endpoint's models are offered at all) lives on its detail page.
//
// It lives under RESOURCES rather than Settings because `provider` is a
// resource kind like any other, and spec ui-shell's rule is that RESOURCES holds
// the kinds with a list UI. It was the only one of the five filed elsewhere.
//
// The page is now nothing but that connection library, rendered through the
// shared DataTable like every other list surface (ConnectionsTable): the page
// itself owns only the header + the add dialog. Editing a connection moved to
// its detail page. Coffer's own engine (which connection + model its memory
// organizer runs on) and its own embedding model live in Settings → Engine:
// both configure Coffer itself rather than being a resource served to agents.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Boxes, Plus } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConnectionsTable } from "@/components/settings/ConnectionsTable";
import { ProviderForm } from "@/components/settings/ProviderForm";
import { useProviders, useCreateProvider } from "@/lib/hooks/useProviders";
import { translateApiError } from "@/lib/api/errors";

export function ModelProvidersPage() {
  const { t } = useTranslation();
  const { data: providers = [], isPending, error } = useProviders();
  const createProvider = useCreateProvider();

  const [adding, setAdding] = useState(false);

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
      <PageHeader
        icon={Boxes}
        title={t("settings.connections.title")}
        subtitle={t("settings.connections.subtitle")}
        actions={
          <Button onClick={() => setAdding(true)}>
            <Plus className="mr-1.5 size-4" />
            {t("settings.connections.add")}
          </Button>
        }
      />

      <ConnectionsTable providers={providers} />

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
    </div>
  );
}
