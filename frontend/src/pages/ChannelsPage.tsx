// frontend/src/pages/ChannelsPage.tsx — spec 009-channels surface.
// Mirrors KnowledgeBasesPage: PageHeader + welcome/loading/error/table; the
// Add-channel header action appears only once channels exist — the empty
// state's welcome panel carries the Add call-to-action instead. Registration
// happens in a modal dialog (AddChannelDialog).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Radio } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AddChannelDialog } from "@/kinds/channel/AddChannelDialog";
import { ChannelsTable } from "@/kinds/channel/ChannelsTable";
import { ChannelWelcomePanel } from "@/kinds/channel/ChannelWelcomePanel";
import { translateApiError } from "@/lib/api/errors";
import { useChannels } from "@/lib/hooks/useChannels";

export function ChannelsPage() {
  const { t } = useTranslation();
  const { data: items, isPending, error } = useChannels();
  const [showAdd, setShowAdd] = useState(false);
  const hasItems = (items ?? []).length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Radio}
        title={t("channels.title")}
        subtitle={t("channels.subtitle")}
        actions={
          hasItems ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="mr-1 size-4" /> {t("channels.add")}
            </Button>
          ) : null
        }
      />

      <AddChannelDialog open={showAdd} onOpenChange={setShowAdd} />

      {isPending ? (
        <Card className="paper-card">
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card className="paper-card border-destructive/40">
          <CardHeader>
            <CardTitle className="font-serif text-destructive">
              {t("channels.loadFailed")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !hasItems ? (
        <ChannelWelcomePanel onAdd={() => setShowAdd(true)} />
      ) : (
        <ChannelsTable items={items ?? []} />
      )}
    </div>
  );
}
