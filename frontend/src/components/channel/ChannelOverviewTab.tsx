// frontend/src/components/channel/ChannelOverviewTab.tsx
// A channel's Overview, one column: who can use it (the paired owners: add,
// remove), which agents it drives — the default agent a new conversation
// starts on and the shared reach control for the agents it may drive — and one
// link to the conversations it started. It lists no messages and no
// conversations: Conversations, filtered by this channel, is where those are read.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentSelect } from "@/components/agents/AgentSelect";
import { ScopeControl } from "@/components/ScopeControl";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { channelConversationsHref } from "@/lib/channels/tabs";
import type { ChannelPerson, ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { CHANNEL_KIND } from "@/lib/hooks/useChannels";
import { ChannelPeopleList } from "./ChannelPeopleList";

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-setting-row items-center justify-between gap-6 border-t border-border-subtle py-2.5">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-medium text-text">{label}</span>
        {hint ? <span className="text-xs text-text-muted">{hint}</span> : null}
      </div>
      <div className="flex shrink-0 items-center">{children}</div>
    </div>
  );
}

interface Props {
  channel: ResourceOut;
  status: ChannelStatus | undefined;
  onAdd: () => void;
  onRemove: (person: ChannelPerson) => void;
  onDefaultAgentChange: (agentUid: string) => void;
}

export function ChannelOverviewTab({
  channel,
  status,
  onAdd,
  onRemove,
  onDefaultAgentChange,
}: Props) {
  const { t } = useTranslation();
  const people = status?.people ?? [];
  const defaultAgent =
    typeof channel.config.default_agent === "string" ? channel.config.default_agent : "";

  return (
    <div className="flex max-w-form flex-col gap-8" data-testid="channel-overview">
      <SettingsSection
        title={t("channels.overview.who.title")}
        description={t("channels.overview.who.onlyOwner")}
        headingLevel={3}
      >
        <ChannelPeopleList
          people={people}
          canAdd={status !== undefined}
          onAdd={onAdd}
          onRemove={onRemove}
        />
      </SettingsSection>

      <SettingsSection
        title={t("channels.overview.agents.title")}
        description={t("channels.overview.agents.help")}
        headingLevel={3}
      >
        <Row label={t("channels.overview.agents.default")}>
          <AgentSelect
            label={t("channels.overview.agents.default")}
            value={defaultAgent}
            onChange={onDefaultAgentChange}
          />
        </Row>
        <Row
          label={t("channels.overview.agents.reach")}
          hint={t("channels.overview.agents.reachHint")}
        >
          <ScopeControl kind={CHANNEL_KIND} uid={channel.uid} enabled={channel.enabled} />
        </Row>
      </SettingsSection>

      <Link
        to={channelConversationsHref(channel.uid)}
        data-testid="channel-conversations-link"
        className="w-fit text-sm font-label text-accent-text hover:underline"
      >
        {t("channels.overview.conversationsLink")}
      </Link>
    </div>
  );
}
