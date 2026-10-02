// frontend/src/components/channel/ChannelOverviewTab.tsx
// A channel's Overview: who can use it (the paired owners: add, remove) and
// which agents it drives — the default agent a new conversation starts on,
// the shared reach control for the agents it may drive, and a link to the
// latest conversations it started (each a link) and every command it answers.
// It lists no messages: every message becomes an ordinary conversation, and
// Conversations is where those are read.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AgentSelect } from "@/components/agents/AgentSelect";
import { Section, SectionStack } from "@/components/Section";
import { ScopeControl } from "@/components/ScopeControl";
import type { ChannelPerson, ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { CHANNEL_KIND } from "@/lib/hooks/useChannels";
import { displayName } from "@/lib/resourceTitle";
import { ChannelCommands } from "./ChannelCommands";
import { ChannelPeopleList } from "./ChannelPeopleList";
import { ChannelRecentConversations } from "./ChannelRecentConversations";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[132px_minmax(0,1fr)] items-center gap-3 border-t border-border-subtle py-2">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="flex min-w-0">{children}</span>
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
    <div className="flex flex-col gap-7">
      <div className="grid items-start gap-7 lg:grid-cols-2">
        <Section
          title={t("channels.overview.who.title")}
          help={t("channels.overview.who.onlyOwner")}
          labelled
        >
          <ChannelPeopleList
            people={people}
            canAdd={status !== undefined}
            onAdd={onAdd}
            onRemove={onRemove}
          />
        </Section>

        <Section
          title={t("channels.overview.agents.title")}
          help={t("channels.overview.agents.help")}
          labelled
        >
          <div className="flex flex-col">
            <Row label={t("channels.overview.agents.default")}>
              <AgentSelect
                label={t("channels.overview.agents.default")}
                value={defaultAgent}
                onChange={onDefaultAgentChange}
              />
            </Row>
            <Row label={t("channels.overview.agents.reach")}>
              <ScopeControl kind={CHANNEL_KIND} uid={channel.uid} enabled={channel.enabled} />
            </Row>
          </div>
        </Section>
      </div>
      <SectionStack>
        <ChannelRecentConversations channelUid={channel.uid} channelName={displayName(channel)} />
        <ChannelCommands commands={status?.commands} />
      </SectionStack>
    </div>
  );
}
