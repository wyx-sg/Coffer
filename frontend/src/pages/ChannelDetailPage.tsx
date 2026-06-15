// frontend/src/pages/ChannelDetailPage.tsx — one channel's operating surface
// (spec 009, User Stories 2 + 8): edit / enable-disable / delete in the header
// (mirrors McpServerDetailPage), a live status card (adapter, paired peer),
// the pairing-code generator, a send-test-message card wired to the notify
// capability, and — for SeaTalk — the callback endpoint to point a tunnel at.
// Status auto-refreshes while the page is open.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Switch } from "@/components/ui/switch";
import { ChannelCallbackCard } from "@/kinds/channel/ChannelCallbackCard";
import {
  ChannelPairingCard,
  ChannelStatusCard,
  ChannelTestMessageCard,
} from "@/kinds/channel/ChannelDetailCards";
import { EditChannelDialog } from "@/kinds/channel/EditChannelDialog";
import {
  useChannelStatus,
  useIssuePairingCode,
  useNotifyChannel,
  CHANNEL_KIND,
} from "@/lib/hooks/useChannels";
import {
  useDeleteResource,
  useDisableResource,
  useEnableResource,
} from "@/lib/hooks/useResourceMutations";
import { useResource } from "@/lib/hooks/useResources";

export function ChannelDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: resource, isPending, error } = useResource(CHANNEL_KIND, name);
  // Poll while the detail page is open so a pairing completed from the IM app
  // (or an adapter restart) shows up without a manual refresh.
  const { data: status } = useChannelStatus(name, { poll: true });
  const pairing = useIssuePairingCode(name);
  const notify = useNotifyChannel(name);
  const enable = useEnableResource();
  const disable = useDisableResource();
  const del = useDeleteResource();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  if (isPending) {
    return (
      <Card className="paper-card">
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (error || !resource) {
    return (
      <Card className="paper-card border-destructive/40">
        <CardHeader>
          <CardTitle className="font-serif text-destructive">
            {t("errors.RESOURCE_NOT_FOUND")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-foreground/80">
            {error instanceof Error ? error.message : t("errors.RESOURCE_NOT_FOUND")}
          </p>
          <Button variant="link" onClick={() => navigate("/channels")}>
            <ArrowLeft className="mr-1 size-4" />
            {t("channels.backToChannels")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const channelType =
    typeof resource.config.channel_type === "string" ? resource.config.channel_type : "telegram";

  return (
    <div className="space-y-6">
      <div className="-ml-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/channels")}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1.5 size-4" /> {t("channels.backToChannels")}
        </Button>
      </div>

      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl tracking-tight">{resource.name}</h1>
          <Badge variant="secondary">{t(`channels.types.${channelType}`, channelType)}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setEditOpen(true)}
            aria-label={t("channels.edit.title")}
          >
            <Pencil className="mr-1.5 size-3.5" /> {t("common.edit")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setDeleteOpen(true)}
            aria-label={t("channels.deleteTitle")}
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
          </Button>
          <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-card px-3">
            <Switch
              checked={resource.enabled}
              onCheckedChange={(checked) => {
                const m = checked ? enable : disable;
                m.mutate({ kind: CHANNEL_KIND, name });
              }}
              disabled={enable.isPending || disable.isPending}
              aria-label={resource.enabled ? t("common.enabled") : t("common.disabled")}
            />
            <span className="text-sm font-medium">
              {resource.enabled ? t("common.enabled") : t("common.disabled")}
            </span>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChannelStatusCard status={status} />
        <ChannelPairingCard
          code={pairing.data}
          isPending={pairing.isPending}
          onGenerate={() => pairing.mutate()}
        />
      </div>

      {status?.callback ? (
        <ChannelCallbackCard name={name} callback={status.callback} />
      ) : null}

      <ChannelTestMessageCard
        hasPeer={status?.peer != null}
        isPending={notify.isPending}
        onSend={(text) => notify.mutate(text)}
      />

      <EditChannelDialog open={editOpen} onOpenChange={setEditOpen} resource={resource} />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("channels.deleteTitle")}
        description={t("channels.deleteConfirm", { name })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          del.mutate({ kind: CHANNEL_KIND, name }, { onSuccess: () => navigate("/channels") });
        }}
      />
    </div>
  );
}
