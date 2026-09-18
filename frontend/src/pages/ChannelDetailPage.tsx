// frontend/src/pages/ChannelDetailPage.tsx — one channel's operating surface
// (spec channels, User Stories 2 + 8): the shared PageHeader with the platform
// chip beside the name and reach / edit / delete as its actions (mirrors
// McpServerDetailPage), a live status card (adapter, paired peer), the machine
// card (which machine runs this channel's adapter), the pairing-code
// generator, a test-delivery card wired to the notify capability, and — for
// SeaTalk — the callback endpoint to point a tunnel at. Status auto-refreshes
// while the page is open.
//
// The header's reach control and the machine card look adjacent and are not:
// reach is which AGENTS this channel may drive, the machine card is which
// MACHINE runs its adapter. The card says so, because a page carrying both is
// exactly where the two get confused.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Pencil, Radio, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ScopeControl } from "@/components/ScopeControl";
import { ChannelCallbackCard } from "@/components/channel/ChannelCallbackCard";
import {
  ChannelPairingCard,
  ChannelTestMessageCard,
} from "@/components/channel/ChannelDetailCards";
import { ChannelStatusCard } from "@/components/channel/ChannelStatusCard";
import { EditChannelDialog } from "@/components/channel/EditChannelDialog";
import { translateApiError } from "@/lib/api/errors";
import {
  useChannelStatus,
  useIssuePairingCode,
  useNotifyChannel,
  CHANNEL_KIND,
} from "@/lib/hooks/useChannels";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useResource } from "@/lib/hooks/useResources";

export function ChannelDetailPage() {
  const { t } = useTranslation();
  const { uid = "" } = useParams<{ uid: string }>();
  const navigate = useNavigate();
  const { data: resource, isPending, error } = useResource(uid);
  // Poll while the detail page is open so a pairing completed from the IM app
  // (or an adapter restart) shows up without a manual refresh.
  const { data: status } = useChannelStatus(uid, { poll: true });
  const pairing = useIssuePairingCode(uid);
  const notify = useNotifyChannel(uid);
  const del = useDeleteResource();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const back = { to: "/channels", label: t("channels.backToChannels") };

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-48" />} />
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }
  if (error || !resource) {
    return (
      <div className="space-y-6">
        {/* The channel could not be read, so there is no name to head the
            page with — and a uid is not a name. The heading is the failure. */}
        <PageHeader back={back} title={t("errors.RESOURCE_NOT_FOUND")} />
        <EmptyState
          icon={Radio}
          title={t("errors.RESOURCE_NOT_FOUND")}
          description={error ? translateApiError(t, error) : undefined}
          action={
            <Button asChild variant="outline">
              <Link to="/channels">
                <ArrowLeft className="mr-1.5 size-4" aria-hidden />
                {t("channels.backToChannels")}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  const channelType =
    typeof resource.config.channel_type === "string" ? resource.config.channel_type : "telegram";

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={resource.name}
        badges={
          <Badge variant="secondary">{t(`channels.types.${channelType}`, channelType)}</Badge>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* The same reach control the list row and every other kind's
                detail page carries; it fetches its own scope, since this page
                renders one resource. */}
            <ScopeControl kind={CHANNEL_KIND} uid={uid} enabled={resource.enabled} />
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
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <ChannelStatusCard
          uid={uid}
          name={resource.name}
          config={resource.config}
          status={status}
        />
        <ChannelPairingCard
          code={pairing.data}
          isPending={pairing.isPending}
          onGenerate={() => pairing.mutate()}
        />
      </div>

      {status?.callback ? <ChannelCallbackCard uid={uid} callback={status.callback} /> : null}

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
        description={t("channels.deleteConfirm", { name: resource.name })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          del.mutate({ kind: CHANNEL_KIND, uid }, { onSuccess: () => navigate("/channels") });
        }}
      />
    </div>
  );
}
