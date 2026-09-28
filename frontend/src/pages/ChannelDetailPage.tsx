// frontend/src/pages/ChannelDetailPage.tsx — one channel's operating surface
// (spec channels, User Stories 2 + 8): the shared PageHeader with the platform
// chip beside the name and reach / edit / delete as its actions (mirrors
// McpServerDetailPage), and under it ONE card — ChannelOverviewCard — holding
// the status strip (adapter, SeaTalk connection, machine), the account
// (paired owner and pairing) and test delivery. Status auto-refreshes while
// the page is open.
//
// The header's reach control and the strip's machine picker look adjacent and
// are not: reach is which AGENTS this channel may drive, the picker is which
// MACHINE runs its adapter. The picker's "?" says so, because a page carrying
// both is exactly where the two get confused.
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
import { ChannelOverviewCard } from "@/components/channel/ChannelOverviewCard";
import { EditChannelDialog } from "@/components/channel/EditChannelDialog";
import { translateApiError } from "@/lib/api/errors";
import { useChannelStatus, CHANNEL_KIND } from "@/lib/hooks/useChannels";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useResource } from "@/lib/hooks/useResources";
import { displayName } from "@/lib/resourceTitle";
import { ResourceLabel } from "@/components/resource/ResourceLabel";

export function ChannelDetailPage() {
  const { t } = useTranslation();
  const { uid = "" } = useParams<{ uid: string }>();
  const navigate = useNavigate();
  const { data: resource, isPending, error } = useResource(uid);
  // Poll while the detail page is open so a pairing completed from the IM app
  // (or an adapter restart) shows up without a manual refresh.
  const { data: status } = useChannelStatus(uid, { poll: true });
  const del = useDeleteResource();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const back = { to: "/channels", label: t("channels.backToChannels") };

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-48" />} />
        <Skeleton className="h-72 w-full" />
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
        title={<ResourceLabel resource={resource} heading />}
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

      <ChannelOverviewCard
        uid={uid}
        name={displayName(resource)}
        config={resource.config}
        status={status}
      />

      <EditChannelDialog open={editOpen} onOpenChange={setEditOpen} resource={resource} />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("channels.deleteTitle")}
        description={t("channels.deleteConfirm", { name: displayName(resource) })}
        confirmLabel={t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          del.mutate({ kind: CHANNEL_KIND, uid }, { onSuccess: () => navigate("/channels") });
        }}
      />
    </div>
  );
}
