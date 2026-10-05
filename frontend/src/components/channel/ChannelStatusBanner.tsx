// frontend/src/components/channel/ChannelStatusBanner.tsx
// Between the channel header and its tabs: what is wrong (or deliberately
// quiet), in plain words, with the one button that fixes it inside (boards
// 3.2.06–17). A problem is a banner — warning, danger, or info for "pair it" —
// and its button is the fix: Reconnect now, Replace token, Take it back,
// Retry, Open Secrets, Run it here, Generate pairing code. A missing SeaTalk
// SDK is the one with two ways forward: the person downloads it (it sits
// behind their SeaTalk login) and hands the rest to an agent (`status.handoff`),
// offered as a "Hand off to <Agent> ▾" split button beside Retry.
// Two states are not problems and get a quiet grey box instead: the channel is
// off, or another Mac runs it. A healthy channel shows nothing. The daemon's
// diagnostics (a setting the platform will not honour) follow as their own
// banners.
import { Trans, useTranslation } from "react-i18next";
import { AlertCircle, AlertTriangle, Info } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import type { ChannelStateKey, ChannelView } from "@/lib/channels/channelState";
import { channelPlatform } from "@/lib/channels/channelState";
import { displayName } from "@/lib/resourceTitle";
import type { ChannelCommand } from "./ChannelDetailHeader";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { useMachineName } from "./channelLabels";
import { platformLabel } from "./PlatformMark";

type Variant = "info" | "warning" | "error";

/** SeaTalk's page for the SDK, where the person downloads it. */
const SEATALK_SDK_DOCS = "https://open.seatalk.io/docs/WebSocket-Event-Callback";

const VARIANT: Partial<Record<ChannelStateKey, Variant>> = {
  unavailable: "warning",
  unbound: "error",
  unknownMachine: "error",
  reconnecting: "warning",
  kicked: "error",
  sdkMissing: "error",
  connectFailed: "error",
  unreachable: "warning",
  waitingApproval: "warning",
  approvalRefused: "error",
  stopped: "error",
  notPaired: "info",
};

const ICON = { info: Info, warning: AlertTriangle, error: AlertCircle } as const;

/** The copy key a state reads from: a rejected token reads the same whether the
 *  platform said so or the adapter simply stopped. */
function copyKey(state: ChannelStateKey, platform: string): string {
  if (state === "connectFailed" || state === "stopped")
    return `tokenRejected.${platform === "seatalk" ? "seatalk" : "telegram"}`;
  if (state === "unbound") return "unknownMachine";
  return state;
}

interface Props {
  channel: ResourceOut;
  view: ChannelView;
  status: ChannelStatus | undefined;
  /** Runs the banner's fix (Reconnect now, Take it back, Run it here, …). */
  onCommand: (command: ChannelCommand) => void;
  /** Opens the pairing dialog; offered in a not-paired channel's banner. */
  onPair: () => void;
  busy?: boolean;
}

export function ChannelStatusBanner({ channel, view, status, onCommand, onPair, busy }: Props) {
  const { t } = useTranslation();
  const machineName = useMachineName();
  const platformKey = channelPlatform(channel.config);
  const vars = {
    platform: platformLabel(platformKey),
    machine: machineName(view.runsOn),
    appId: typeof channel.config.app_id === "string" ? channel.config.app_id : "",
    name: displayName(channel),
  };
  const variant = VARIANT[view.state];
  const Icon = variant ? ICON[variant] : null;
  const handoff = view.state === "sdkMissing" ? (status?.handoff?.prompt ?? null) : null;
  const detail =
    view.state === "unavailable" || handoff ? null : (status?.inbound?.websocket_error ?? null);
  const diagnostics = status?.diagnostics ?? [];
  const key = copyKey(view.state, platformKey);
  const fix = view.state === "notPaired" ? null : view.primary;
  const fixLabel =
    fix === "replaceSecret"
      ? t(`channels.actions.${platformKey === "telegram" ? "replaceToken" : "replaceSecret"}`)
      : fix
        ? t(`channels.actions.${fix}`)
        : null;

  const body =
    view.state === "sdkMissing" ? (
      <Trans
        i18nKey="channels.banner.sdkMissing.body"
        components={{
          portal: (
            <a href={SEATALK_SDK_DOCS} target="_blank" rel="noreferrer" className="underline" />
          ),
        }}
      />
    ) : (
      t(`channels.banner.${key}.body`, vars)
    );

  return (
    <>
      {variant && Icon ? (
        <Alert variant={variant} data-testid="channel-banner" data-state={view.state}>
          <Icon aria-hidden />
          <AlertTitle>{t(`channels.banner.${key}.title`, vars)}</AlertTitle>
          <AlertDescription>
            <p>{body}</p>
            {detail ? <p className="mt-1 break-words font-mono text-2xs">{detail}</p> : null}
            {fixLabel || view.state === "notPaired" ? (
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                {view.state === "notPaired" ? (
                  <Button size="sm" variant="outline" onClick={onPair}>
                    {t("channels.banner.notPaired.action")}
                  </Button>
                ) : fix && fixLabel ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => onCommand(fix)}
                  >
                    {fixLabel}
                  </Button>
                ) : null}
                {handoff ? <AgentHandoff prompt={handoff} size="sm" /> : null}
              </div>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}
      {view.state === "off" || view.state === "elsewhere" ? (
        <QuietBox view={view} vars={vars} busy={busy} onCommand={onCommand} />
      ) : null}
      {diagnostics.map((d) => (
        // A setting that reads correctly here and does nothing in the chat
        // (spec channels/telegram "Report privacy mode that defeats the group
        // configuration").
        <Alert key={d.code} variant="warning" data-testid="channel-diagnostic">
          <AlertTriangle aria-hidden />
          <AlertDescription>
            <p>{d.message}</p>
          </AlertDescription>
        </Alert>
      ))}
    </>
  );
}

/** Off, or run by another Mac: nothing is wrong, so no banner — a neutral box
 *  with one small button to change it (boards 3.2.13, 3.2.14). */
function QuietBox({
  view,
  vars,
  busy,
  onCommand,
}: {
  view: ChannelView;
  vars: { name: string; machine: string };
  busy?: boolean;
  onCommand: (command: ChannelCommand) => void;
}) {
  const { t } = useTranslation();
  const off = view.state === "off";
  return (
    <div
      data-testid="channel-quiet"
      data-state={view.state}
      className="flex items-center gap-3 rounded-lg border border-border bg-surface-sunken px-3.5 py-3"
    >
      <p className="min-w-0 flex-1 text-sm text-text">
        {off ? t("channels.quiet.off", vars) : t("channels.quiet.elsewhere", vars)}
      </p>
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => onCommand(off ? "turnOn" : "runHereConfirm")}
      >
        {off ? t("channels.actions.turnOn") : t("channels.actions.runHereConfirm")}
      </Button>
    </div>
  );
}
