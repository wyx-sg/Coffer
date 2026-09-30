// frontend/src/components/channel/ChannelOverviewTab.tsx
// A channel's Overview: who can use it (the paired owner, and re-pairing) and
// which agents it drives — the default agent a new conversation starts on,
// the shared reach control for the agents it may drive, and a link to the
// conversations it started. It lists no messages: every message becomes an
// ordinary conversation, and Conversations is where those are read.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";

import { AgentSelect } from "@/components/agents/AgentSelect";
import { ScopeControl } from "@/components/ScopeControl";
import { Button } from "@/components/ui/button";
import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { channelConversationsHref } from "@/lib/channels/tabs";
import { CHANNEL_KIND } from "@/lib/hooks/useChannels";
import { formatDateTime } from "@/lib/utils";
import { channelHeading } from "./channelLabels";

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : name.slice(0, 2);
  return letters.toUpperCase();
}

function Section({ title, meta, children }: { title: string; meta?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2.5" aria-label={title}>
      <div className="flex min-h-[26px] items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {meta ? <span className="text-xs text-text-muted">{meta}</span> : null}
      </div>
      {children}
    </section>
  );
}

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
  /** The pairing code panel, shown under the owner once a new code is out,
   *  or in place of the owner when the banner is not already showing it. */
  pairing: ReactNode;
  showPairing: boolean;
  onRepair: () => void;
  onDefaultAgentChange: (agentUid: string) => void;
}

export function ChannelOverviewTab({
  channel,
  status,
  pairing,
  showPairing,
  onRepair,
  onDefaultAgentChange,
}: Props) {
  const { t } = useTranslation();
  const peer = status?.peer ?? null;
  const defaultAgent =
    typeof channel.config.default_agent === "string" ? channel.config.default_agent : "";

  return (
    <div className="grid items-start gap-7 lg:grid-cols-2">
      <Section
        title={t("channels.overview.who.title")}
        meta={peer ? t("channels.overview.who.oneOwner") : undefined}
      >
        {peer ? (
          <div className="flex min-h-[46px] items-center gap-2.5 border-t border-border-subtle">
            <span
              aria-hidden
              className="inline-flex size-[26px] shrink-0 items-center justify-center rounded-md bg-chip text-2xs font-semibold text-text-muted"
            >
              {initials(peer.display_name)}
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-label" data-testid="channel-owner">
                {peer.display_name}
              </span>
              <span className="text-xs text-text-muted">
                {t("channels.overview.who.ownerLine", { date: formatDateTime(peer.paired_at) })}
              </span>
            </span>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={onRepair}>
              {t("channels.overview.who.repair")}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-text-muted">{t("channels.overview.who.nobody")}</p>
        )}
        {showPairing ? pairing : null}
        {peer ? (
          <p className="text-xs text-text-muted">{t("channels.overview.who.onlyOwner")}</p>
        ) : null}
      </Section>

      <Section title={t("channels.overview.agents.title")}>
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
        <p className="text-xs leading-normal text-text-muted">
          {t("channels.overview.agents.help", { agentCommand: "/agent" })}
        </p>
        <Link
          to={channelConversationsHref(channel.uid)}
          className="inline-flex w-fit items-center gap-1 text-sm font-label text-accent-text hover:underline"
          data-testid="channel-conversations-link"
        >
          {t("channels.overview.conversations")}
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
        <span className="text-xs text-text-muted">
          {t("channels.overview.conversationsHint", { name: channelHeading(channel) })}
        </span>
      </Section>
    </div>
  );
}
