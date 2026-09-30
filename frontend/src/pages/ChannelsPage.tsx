// frontend/src/pages/ChannelsPage.tsx — spec channels "Manage channels from the Channels page and the CLI".
// The Channels page is the channel list beside the open channel: `/channels`,
// `/channels/<uid>` and `/channels/<uid>/settings` all render it — the list on
// the left (grouped by state), the open channel on the right with its
// Overview and Settings tabs. `/channels` alone opens the first channel. With
// no channel yet, the page is the first-run welcome, whose platform cards open
// Add channel at its Connect step. Channels are addressed by uid (renamable).
import { useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, Radio } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { AddChannelDialog } from "@/components/channel/AddChannelDialog";
import { ChannelDetailPane } from "@/components/channel/ChannelDetailPane";
import { ChannelFirstRun } from "@/components/channel/ChannelFirstRun";
import { ChannelList } from "@/components/channel/ChannelList";
import { CHANNEL_GROUPS } from "@/components/channel/channelState";
import { Button } from "@/components/ui/button";
import type { ChannelType } from "@/lib/api/channels";
import { translateApiError } from "@/lib/api/errors";
import { useDetailTab } from "@/lib/detailTabs";
import { CHANNEL_TABS, DEFAULT_CHANNEL_TAB, channelPath } from "@/lib/channels/tabs";
import { useChannels, useChannelViews } from "@/lib/hooks/useChannels";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";

export function ChannelsPage() {
  const { t } = useTranslation();
  // Adapters restart and pairings land while the page is open: the change
  // feed refreshes the list's statuses; the open channel also polls its own.
  useDaemonEvents();
  const { uid = "" } = useParams<{ uid?: string }>();
  const navigate = useNavigate();
  const list = useChannels();
  const channels = list.data ?? [];
  const views = useChannelViews(channels);
  const [addOpen, setAddOpen] = useState(false);
  const [addPlatform, setAddPlatform] = useState<ChannelType | null>(null);
  const current = channels.find((c) => c.uid === uid) ?? null;
  const basePath = uid ? channelPath(uid) : "/channels";
  const [tab, setTab] = useDetailTab(CHANNEL_TABS, DEFAULT_CHANNEL_TAB, basePath, {
    enabled: current !== null,
  });

  const openAdd = (platform: ChannelType | null) => {
    setAddPlatform(platform);
    setAddOpen(true);
  };
  const dialog = (
    <AddChannelDialog open={addOpen} onOpenChange={setAddOpen} initialPlatform={addPlatform} />
  );
  const header = (
    <PageHeader
      icon={Radio}
      title={t("channels.title")}
      badges={
        channels.length > 0 ? (
          <span className="text-sm text-text-muted">{channels.length}</span>
        ) : null
      }
      actions={
        <Button onClick={() => openAdd(null)}>
          <Plus aria-hidden /> {t("channels.add.button")}
        </Button>
      }
    />
  );

  // `/channels` alone opens the first channel, in the order the list shows.
  if (!uid && channels.length > 0) {
    const first =
      CHANNEL_GROUPS.flatMap((g) => channels.filter((c) => views.get(c.uid)?.group === g))[0] ??
      channels[0];
    return <Navigate replace to={channelPath(first.uid)} />;
  }

  if (!list.isPending && !list.error && channels.length === 0) {
    return (
      <>
        <div className="space-y-6">
          {header}
          <ChannelFirstRun onChoose={openAdd} />
        </div>
        {dialog}
      </>
    );
  }

  let pane: JSX.Element;
  if (list.error) {
    pane = (
      <EmptyState
        tone="error"
        icon={Radio}
        title={t("channels.loadFailed")}
        description={translateApiError(t, list.error)}
        action={
          <Button variant="outline" onClick={() => void list.refetch()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  } else if (list.isPending) {
    pane = <PageFallback />;
  } else if (current) {
    pane = (
      <ChannelDetailPane
        key={current.uid}
        channel={current}
        tab={tab}
        onTabChange={setTab}
        onDeleted={async () => {
          // Leave only once the list no longer holds it, or `/channels` would
          // reopen the channel that was just deleted.
          await list.refetch();
          navigate("/channels", { replace: true });
        }}
      />
    );
  } else {
    pane = (
      <EmptyState
        icon={Radio}
        title={t("channels.notFound")}
        description={t("channels.notFoundBody")}
      />
    );
  }

  return (
    <>
      {/* Full-bleed like Skills: the two panes each scroll on their own. */}
      <div className="-mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10">
        <div className="shrink-0 border-b border-border-subtle px-6 pb-4 pt-5">{header}</div>
        <SplitView
          storageKey="channels.list"
          defaultListWidth={292}
          label={t("splitView.resizeList")}
          className="min-h-0 flex-1"
          detailClassName="overflow-y-auto"
          list={
            <ChannelList
              channels={channels}
              views={views}
              isLoading={list.isPending}
              selectedUid={current?.uid ?? null}
              hrefFor={(id) => channelPath(id, tab)}
            />
          }
          detail={<div className="px-7 pb-5 pt-5">{pane}</div>}
        />
      </div>
      {dialog}
    </>
  );
}
